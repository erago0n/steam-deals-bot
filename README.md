# Steam Deals Bot 🎮🔥

A Telegram bot that scans **every discounted game on Steam**, picks the ones worth buying and posts them to a Telegram channel, with a generated cover image for the daily digest. Runs for free in the cloud on GitHub Actions.

- **Full coverage:** scans the whole Steam specials list (thousands of games) via the Steam store search, with local (UAH) prices
- **Quality filter:** minimum discount, minimum number of reviews and % positive, so no shovelware
- **Record lows:** checks the all-time lowest price (CheapShark) and highlights record deals
- **Two post types:**
  - single post for every record-low deal: cover, Ukrainian description, UAH + USD price, review score
  - 1-2 digest posts a day: **a generated cover** (wall of game covers, big title, neon date) and the list of linked games in an expandable quote
- **No duplicates:** SQLite state; the digest only shows deals that were not in a previous digest
- **Free cloud hosting:** GitHub Actions runs it every 30 minutes and keeps the state in a `state` branch
- **Optional always-on mode** with bot commands `/top`, `/digest`, `/filter`

## Run in the cloud (GitHub Actions, free)

1. Fork / push this repo to GitHub (public repos get free Actions minutes).
2. Add the bot token as a secret: **Settings → Secrets and variables → Actions → New repository secret** → `BOT_TOKEN`.
3. Optionally add **variables** (same page, *Variables* tab): `CHANNEL_ID`, `MIN_DISCOUNT`, `MIN_REVIEWS`, `MIN_POSITIVE`, `POSTS_PER_CHECK`, `MAX_SINGLES_PER_DAY`, `DIGEST_HOURS`.
4. Open **Actions → Steam deals bot → Run workflow** for the first run. After that it runs every 30 minutes by itself.

## Run locally (always-on, with commands)

```bash
cp .env.example .env   # fill BOT_TOKEN and CHANNEL_ID
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main     # or: python -m bot.run_once  for a single cycle
```

Docker:

```bash
docker build -t steam-deals-bot .
docker run -d --restart unless-stopped --env-file .env -v $(pwd)/data:/app/data steam-deals-bot
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | — | Token from @BotFather |
| `CHANNEL_ID` | — | `@channel_name` or numeric id `-100…` |
| `MIN_DISCOUNT` | `50` | Minimum discount, % |
| `MIN_REVIEWS` | `5000` | Minimum number of Steam user reviews |
| `MIN_POSITIVE` | `70` | Minimum % of positive reviews |
| `MAX_SCAN` | `2000` | How many discounted games to scan per run (most relevant first) |
| `POSTS_PER_CHECK` | `1` | Single posts per run |
| `MAX_SINGLES_PER_DAY` | `2` | Cap on single record-low posts per day |
| `RECORDS_ONLY` | `true` | Single posts only for all-time-low prices |
| `DIGEST_HOURS` | `13,20` | Digest post hours (Kyiv time), empty to disable |

## Project structure

```
bot/
  sources.py     # Steam search (all discounts), CheapShark record lows, Steam appdetails
  formatting.py  # Telegram HTML templates (single post, digest captions)
  image.py       # digest cover image (Pillow)
  core.py        # one posting cycle: single posts + daily digest
  run_once.py    # cloud entry point (GitHub Actions)
  main.py        # always-on mode with bot commands
  storage.py     # SQLite: posted deals + cache
assets/fonts/    # Oswald (SIL Open Font License)
.github/workflows/bot.yml  # runs every 30 min, saves state to the "state" branch
```

## Tech

Python 3.11+, aiogram 3, aiohttp, Pillow, SQLite, GitHub Actions, Docker.
