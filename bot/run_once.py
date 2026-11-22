"""Cloud entry point: run one posting cycle and exit.

Used by the GitHub Actions workflow (.github/workflows/bot.yml), which runs this every
30 minutes and keeps data/deals.db between runs.

Run:  python -m bot.run_once
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_settings
from .core import run_cycle
from .storage import PostedDeals


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = load_settings()
    store = PostedDeals(s.db_path)
    bot = Bot(s.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await run_cycle(bot, s, store)
    finally:
        store.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
