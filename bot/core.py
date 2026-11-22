"""One posting cycle, shared by the always-on bot (main.py) and the cloud job (run_once.py).

Posting plan:
- 1-2 digest posts a day (DIGEST_HOURS): cover image + expandable list of popular deals
  that were not in an earlier digest;
- now and then a single post for a record-low price (at most MAX_SINGLES_PER_DAY).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from .config import Settings
from .formatting import KYIV, digest_caption, format_deal
from .image import build_digest_image
from .sources import Deal, enrich_many, fetch_deals
from .storage import PostedDeals

log = logging.getLogger("steam_deals_bot")


async def current_deals(s: Settings, store: PostedDeals) -> list[Deal]:
    return await fetch_deals(
        store, min_discount=s.min_discount, min_reviews=s.min_reviews,
        min_positive=s.min_positive, max_scan=s.max_scan,
    )


async def _send(call):
    """Run a Telegram call, waiting once if we hit Telegram's flood limit."""
    try:
        return await call()
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        return await call()


# ---------- occasional single posts for record lows ----------

async def post_deal(bot: Bot, chat_id: str | int, deal: Deal, signature: str | None) -> None:
    text = format_deal(deal, signature)
    try:
        await _send(lambda: bot.send_photo(chat_id, deal.image, caption=text))
    except TelegramBadRequest as exc:  # broken image URL -> fall back to text
        log.info("Photo failed for %s (%s), sending text", deal.title, exc)
        await _send(lambda: bot.send_message(chat_id, text, disable_web_page_preview=True))


async def post_singles(bot: Bot, s: Settings, store: PostedDeals, deals: list[Deal]) -> int:
    today = datetime.now(KYIV).date()
    counter = f"singles:{today}"
    done_today = int(store.get(counter) or 0)
    room = min(s.posts_per_check, s.max_singles_per_day - done_today)
    if room <= 0:
        return 0
    wanted = [d for d in deals if d.is_record or not s.records_only]
    fresh = [d for d in wanted if not store.is_posted(f"p:{d.key}")][:room]
    for deal in await enrich_many(fresh):
        await post_deal(bot, s.channel_id, deal, s.signature)
        store.mark_posted(f"p:{deal.key}")
        done_today += 1
        store.set(counter, str(done_today))
        await asyncio.sleep(3)
    log.info("Single posts: %d (today %d/%d)", len(fresh), done_today, s.max_singles_per_day)
    return len(fresh)


# ---------- digest ----------

async def send_digest(bot: Bot, chat_id: str | int, s: Settings, deals: list[Deal],
                      store: PostedDeals | None = None) -> bool:
    """One digest post: cover image + caption with the list.

    With a store, only deals that were not in an earlier digest are used (and remembered);
    without one (preview), all current deals are used.
    """
    today = datetime.now(KYIV).date()
    pool = [d for d in deals if store is None or not store.is_posted(f"dg:{d.key}")]
    caption, used = digest_caption(pool, today, s.signature)
    if not used:
        return False
    image = await build_digest_image(used, today, s.signature, count=len(used))
    photo = BufferedInputFile(image, filename=f"znyzhky-{today}.jpg")
    await _send(lambda: bot.send_photo(chat_id, photo, caption=caption))
    if store is not None:
        for d in used:
            store.mark_posted(f"dg:{d.key}")
    return True


def due_digest_slot(s: Settings, store: PostedDeals) -> tuple[str, list[str]] | None:
    """The latest digest slot that is due today, plus earlier missed slots to skip."""
    now = datetime.now(KYIV)
    due = [h for h in sorted(s.digest_hours) if now.hour >= h and not store.is_posted(f"digest:{now.date()}:{h}")]
    if not due:
        return None
    keys = [f"digest:{now.date()}:{h}" for h in due]
    return keys[-1], keys[:-1]  # never post several digests at once after a pause


# ---------- one full cycle ----------

async def run_cycle(bot: Bot, s: Settings, store: PostedDeals) -> None:
    deals = await current_deals(s, store)
    slot = due_digest_slot(s, store)
    if slot:
        key, skipped = slot
        posted = await send_digest(bot, s.channel_id, s, deals, store)
        for k in [key, *skipped]:
            store.mark_posted(k)
        log.info("Digest %s: %s", key, "posted" if posted else "nothing new to post")
    await post_singles(bot, s, store, deals)
    store.forget_older_than(days=30)
