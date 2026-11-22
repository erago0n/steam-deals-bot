"""Steam Deals Bot: posts the best Steam discounts to a Telegram channel.

Run:  python -m bot.main
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .config import Settings, load_settings
from .formatting import format_deal, format_top
from .sources import Deal, fetch_all_deals
from .storage import PostedDeals

log = logging.getLogger("steam_deals_bot")


def passes_filter(deal: Deal, s: Settings) -> bool:
    return deal.discount >= s.min_discount and deal.new_price <= s.max_price


async def post_deal(bot: Bot, chat_id: str, deal: Deal) -> None:
    text = format_deal(deal)
    if deal.image:
        try:
            await bot.send_photo(chat_id, deal.image, caption=text)
            return
        except TelegramBadRequest as exc:  # broken image URL -> fall back to text
            log.info("Photo failed for %s (%s), sending text", deal.title, exc)
    await bot.send_message(chat_id, text)


async def check_and_post(bot: Bot, s: Settings, store: PostedDeals) -> int:
    deals = [d for d in await fetch_all_deals(s.country) if passes_filter(d, s)]
    posted = 0
    for deal in deals:
        if posted >= s.posts_per_check:
            break
        if store.is_posted(deal.key):
            continue
        await post_deal(bot, s.channel_id, deal)
        store.mark_posted(deal.key)
        posted += 1
        await asyncio.sleep(3)  # stay well under Telegram's rate limits
    log.info("Checked %d deals, posted %d new", len(deals), posted)
    return posted


async def scheduler(bot: Bot, s: Settings, store: PostedDeals) -> None:
    while True:
        try:
            await check_and_post(bot, s, store)
            store.forget_older_than(days=30)
        except Exception:
            log.exception("Check failed, will retry next cycle")
        await asyncio.sleep(s.check_every_min * 60)


def build_dispatcher(s: Settings, store: PostedDeals) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(msg: Message) -> None:
        await msg.answer(
            "👋 Привіт! Я шукаю найкращі знижки в Steam.\n\n"
            "/top — топ знижок прямо зараз\n"
            f"/filter — поточний фільтр\n\n"
            f"Нові знижки публікуються в каналі {s.channel_id}"
        )

    @dp.message(Command("top"))
    async def top(msg: Message) -> None:
        deals = [d for d in await fetch_all_deals(s.country) if passes_filter(d, s)]
        await msg.answer(format_top(deals), disable_web_page_preview=True)

    @dp.message(Command("filter"))
    async def show_filter(msg: Message) -> None:
        await msg.answer(
            f"⚙️ Знижка від <b>{s.min_discount}%</b>, ціна до <b>${s.max_price:g}</b>, "
            f"перевірка кожні <b>{s.check_every_min} хв</b>"
        )

    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = load_settings()
    store = PostedDeals(s.db_path)
    bot = Bot(s.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(s, store)

    asyncio.create_task(scheduler(bot, s, store))
    try:
        await dp.start_polling(bot)
    finally:
        store.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
