# Steam Deals Bot 🎮🔥

A Telegram bot that finds the best Steam discounts and auto-posts them to a Telegram channel.

- **Two free data sources, no API keys:** Steam Store specials + CheapShark (Steam deals with user ratings)
- **Smart filters:** minimum discount %, maximum price
- **No duplicates:** posted deals are stored in SQLite; a game can be posted again in a future sale
- **Rich posts:** cover image, old vs new price, discount %, Steam rating, sale end date, buy link
- **Bot commands:** `/top` shows the current best deals, `/filter` shows the active filter
- **Fault-tolerant:** if one source is down, the other keeps working; errors never stop the loop
- **Docker-ready:** one command to deploy on any VPS

## Example post

```
🔥🔥🔥 Battlefield 3

💸 $39.99 → $1.99  (−95%)
⭐ Mostly Positive (70%)

🛒 Купити в Steam
```

## Quick start

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create a Telegram channel and add the bot as an **admin** (permission to post).
3. Configure:
   ```bash
   cp .env.example .env   # then fill BOT_TOKEN and CHANNEL_ID
   ```
4. Run locally:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m bot.main
   ```
   or with Docker:
   ```bash
   docker build -t steam-deals-bot .
   docker run -d --restart unless-stopped --env-file .env -v $(pwd)/data:/app/data steam-deals-bot
   ```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | — | Token from BotFather |
| `CHANNEL_ID` | — | `@channel_name` or numeric id `-100…` |
| `MIN_DISCOUNT` | `50` | Only post deals with at least this % off |
| `MAX_PRICE` | `30` | Only post deals cheaper than this (USD) |
| `CHECK_EVERY_MIN` | `30` | How often to check for new deals |
| `POSTS_PER_CHECK` | `5` | Max posts per check (avoids flooding the channel) |
| `COUNTRY` | `us` | Steam region for prices |

## Project structure

```
bot/
  sources.py     # Steam + CheapShark fetchers → unified Deal objects
  storage.py     # SQLite de-duplication
  formatting.py  # Telegram HTML message templates
  config.py      # .env settings
  main.py        # aiogram bot, commands and scheduler
```

Adding another store (PlayStation Store, GOG, Epic) = one new fetch function in `sources.py`.

## Tech

Python 3.11+, aiogram 3, aiohttp, SQLite, Docker.
