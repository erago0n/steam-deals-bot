"""Settings come from environment variables (or a .env file next to the project)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    bot_token: str
    channel_id: str  # "@my_channel" or "-100123..."
    min_discount: int = 50
    max_price: float = 30.0
    check_every_min: int = 30
    posts_per_check: int = 5
    country: str = "us"
    db_path: str = "data/deals.db"


def load_settings() -> Settings:
    _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.environ.get("BOT_TOKEN", "")
    channel = os.environ.get("CHANNEL_ID", "")
    if not token or not channel:
        raise SystemExit("Set BOT_TOKEN and CHANNEL_ID in .env (see .env.example)")
    return Settings(
        bot_token=token,
        channel_id=channel,
        min_discount=int(os.environ.get("MIN_DISCOUNT", 50)),
        max_price=float(os.environ.get("MAX_PRICE", 30)),
        check_every_min=int(os.environ.get("CHECK_EVERY_MIN", 30)),
        posts_per_check=int(os.environ.get("POSTS_PER_CHECK", 5)),
        country=os.environ.get("COUNTRY", "us"),
        db_path=os.environ.get("DB_PATH", "data/deals.db"),
    )
