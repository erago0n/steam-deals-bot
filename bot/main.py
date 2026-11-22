"""Always-on mode: posting loop + bot commands (/top, /digest, /filter).

For the free cloud mode without commands, see run_once.py and .github/workflows/bot.yml.

Run:  python -m bot.main
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .config import Settings, load_settings
from .core import current_deals, run_cycle, send_digest
from .formatting import format_top
from .storage import PostedDeals

log = logging.getLogger("steam_deals_bot")


async def scheduler(bot: Bot, s: Settings, store: PostedDeals) -> None:
    while True:
        try:
            await run_cycle(bot, s, store)
        except Exception:
            log.exception("Cycle failed, will retry")
        await asyncio.sleep(s.check_every_min * 60)


def build_dispatcher(s: Settings, store: PostedDeals) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(msg: Message) -> None:
        await msg.answer(
            "👋 Привіт! Я шукаю найкращі знижки в Steam.\n\n"
            "/top — топ знижок прямо зараз\n"
            "/digest — показати, як виглядає добірка\n"
            "/filter — поточні налаштування\n\n"
            f"Знижки публікуються в каналі {s.channel_id}"
        )

    @dp.message(Command("top"))
    async def top(msg: Message) -> None:
        await msg.answer("⏳ Шукаю знижки…")
        await msg.answer(format_top(await current_deals(s, store)), disable_web_page_preview=True)

    @dp.message(Command("digest"))
    async def digest_preview(msg: Message) -> None:
        await msg.answer("⏳ Збираю добірку, це займе хвилину…")
        if not await send_digest(msg.bot, msg.chat.id, s, await current_deals(s, store)):
            await msg.answer("Зараз немає знижок, що проходять фільтр 🤷")

    @dp.message(Command("filter"))
    async def show_filter(msg: Message) -> None:
        hours = ", ".join(f"{h}:00" for h in s.digest_hours) or "вимкнена"
        await msg.answer(
            f"⚙️ Знижка від <b>{s.min_discount}%</b>, від <b>{s.min_reviews}</b> відгуків, "
            f"від <b>{s.min_positive}%</b> позитивних\n"
            f"Окремі пости: <b>{'рекордні знижки' if s.records_only else 'всі знижки'}</b>, до {s.max_singles_per_day} на день\n"
            f"Добірки (Київ): <b>{hours}</b>"
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
