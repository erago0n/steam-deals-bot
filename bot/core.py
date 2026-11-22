"""One posting cycle, shared by the always-on bot (main.py) and the cloud job (run_once.py)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from .config import Settings
from .formatting import KYIV, format_deal, split_digest
from .image import build_digest_image
from .sources import Deal, enrich_many, fetch_deals
from .storage import PostedDeals

log = logging.getLogger("steam_deals_bot")


async def current_deals(s: Settings, store: PostedDeals) -> list[Deal]:
    return await fetch_deals(
        store, min_discount=s.min_discount, min_reviews=s.min_reviews,
        min_positive=s.min_positive, max_scan=s.max_scan,
    )


async def _send(coro_factory):
    """Run a Telegram call, waiting once if we hit Telegram's flood limit."""
    try:
        return await coro_factory()
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        return await coro_factory()


# ---------- single posts ----------

async def post_deal(bot: Bot, chat_id: str | int, deal: Deal, signature: str | None) -> None:
    text = format_deal(deal, signature)
    try:
        await _send(lambda: bot.send_photo(chat_id, deal.image, caption=text))
    except TelegramBadRequest as exc:  # broken image URL -> fall back to text
        log.info("Photo failed for %s (%s), sending text", deal.title, exc)
        await _send(lambda: bot.send_message(chat_id, text, disable_web_page_preview=True))


async def post_new_deals(bot: Bot, s: Settings, store: PostedDeals, deals: list[Deal]) -> int:
    wanted = [d for d in deals if d.is_record or not s.records_only]
    fresh = [d for d in wanted if not store.is_posted(f"p:{d.key}")][: s.posts_per_check]
    for deal in await enrich_many(fresh):
        await post_deal(bot, s.channel_id, deal, s.signature)
        store.mark_posted(f"p:{deal.key}")
        await asyncio.sleep(3)
    log.info("Single posts: %d", len(fresh))
    return len(fresh)


# ---------- daily digest ----------

async def send_digest(bot: Bot, chat_id: str | int, s: Settings, deals: list[Deal],
                      store: PostedDeals | None = None) -> int:
    """Post the digest (image + list) in up to s.digest_parts messages.

    With a store, only deals that were not in an earlier digest are used, and they are
    remembered; without one (preview), all current deals are shown.
    """
    today = datetime.now(KYIV).date()
    pool = [d for d in deals if store is None or not store.is_posted(f"dg:{d.key}")]
    parts = split_digest(pool, today, s.digest_parts, s.signature)
    for i, (caption, used) in enumerate(parts, 1):
        image = await build_digest_image(used, today, s.signature, i, len(parts), len(deals))
        photo = BufferedInputFile(image, filename=f"digest-{today}-{i}.jpg")
        await _send(lambda: bot.send_photo(chat_id, photo, caption=caption))
        if store is not None:
            for d in used:
                store.mark_posted(f"dg:{d.key}")
        await asyncio.sleep(3)
    return len(parts)


def digest_due(s: Settings, store: PostedDeals) -> str | None:
    """Return today's digest key if it is time to post it, else None."""
    if s.digest_hour < 0:
        return None
    now = datetime.now(KYIV)
    key = f"digest:{now.date()}"
    if now.hour >= s.digest_hour and not store.is_posted(key):
        return key
    return None


# ---------- one full cycle ----------

async def run_cycle(bot: Bot, s: Settings, store: PostedDeals) -> None:
    deals = await current_deals(s, store)
    await post_new_deals(bot, s, store, deals)
    key = digest_due(s, store)
    if key:
        sent = await send_digest(bot, s.channel_id, s, deals, store)
        store.mark_posted(key)
        log.info("Daily digest posted in %d part(s)", sent)
    store.forget_older_than(days=30)
