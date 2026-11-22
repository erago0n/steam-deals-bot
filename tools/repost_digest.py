"""Re-post today's digest in the current format and delete the old digest message.

Run:  python -m tools.repost_digest <old_message_id>
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_settings
from bot.core import current_deals, send_digest
from bot.storage import PostedDeals


async def main(old_id: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = load_settings()
    store = PostedDeals("data/repost.db")  # throwaway store: show the same top games again
    bot = Bot(s.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        deals = await current_deals(s, store)
        if not await send_digest(bot, s.channel_id, s, deals):
            print("nothing to post, old message kept")
            return
        print("new digest posted")
        await bot.delete_message(s.channel_id, old_id)
        print(f"old message {old_id} deleted")
    finally:
        store.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
