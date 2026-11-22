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


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    channel_id: str  # "@my_channel" or "-100123..."
    # which deals count as interesting
    min_discount: int = 50
    min_reviews: int = 300
    min_positive: int = 70
    max_scan: int = 2000  # how many discounted games to scan per run (most relevant first)
    # single posts
    posts_per_check: int = 2
    records_only: bool = True  # single posts only for all-time-low prices
    # daily digest
    digest_hour: int = 20  # Kyiv time; -1 disables the daily digest
    digest_parts: int = 3  # max digest messages per day (each = image + list)
    # local polling mode only
    check_every_min: int = 30
    db_path: str = "data/deals.db"

    @property
    def signature(self) -> str | None:
        """'@channel' line at the end of every post (only for public channels)."""
        return self.channel_id if self.channel_id.startswith("@") else None


def load_settings() -> Settings:
    _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.environ.get("BOT_TOKEN", "")
    channel = os.environ.get("CHANNEL_ID", "")
    if not token or not channel:
        raise SystemExit("Set BOT_TOKEN and CHANNEL_ID (in .env or environment)")
    return Settings(
        bot_token=token,
        channel_id=channel,
        min_discount=_int("MIN_DISCOUNT", 50),
        min_reviews=_int("MIN_REVIEWS", 300),
        min_positive=_int("MIN_POSITIVE", 70),
        max_scan=_int("MAX_SCAN", 2000),
        posts_per_check=_int("POSTS_PER_CHECK", 2),
        records_only=_flag("RECORDS_ONLY", True),
        digest_hour=_int("DIGEST_HOUR", 20),
        digest_parts=_int("DIGEST_PARTS", 3),
        check_every_min=_int("CHECK_EVERY_MIN", 30),
        db_path=os.environ.get("DB_PATH", "data/deals.db"),
    )
