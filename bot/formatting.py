"""Telegram message templates (HTML parse mode), in Ukrainian."""
from __future__ import annotations

from datetime import date
from html import escape
from zoneinfo import ZoneInfo

from .sources import Deal

KYIV = ZoneInfo("Europe/Kyiv")
MONTHS = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]
KEYCAPS = {str(i): f"{i}️⃣" for i in range(10)}

RECORD = "🟢"
REGULAR = "◼️"

CAPTION_LIMIT = 1000  # photo captions are limited to 1024 characters


def tg_len(text: str) -> int:
    """Length as Telegram counts it (UTF-16 code units, so emoji count double)."""
    return len(text.encode("utf-16-le")) // 2


def keycaps(number: int) -> str:
    """80 -> 8️⃣0️⃣"""
    return "".join(KEYCAPS[ch] for ch in str(number))


def uah(amount: float) -> str:
    return f"{amount:,.0f}₴".replace(",", " ")


def human_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def _game_link(deal: Deal) -> str:
    return f'<a href="{deal.url}">{escape(deal.title)}</a>'


def format_deal(deal: Deal, channel: str | None = None) -> str:
    """Single post about one discount (used for record-low deals)."""
    marker = RECORD if deal.is_record else REGULAR
    headline = (
        f"Рекордна знижка на <b>{escape(deal.title)}</b> у Steam!"
        if deal.is_record
        else f"Знижка на <b>{escape(deal.title)}</b> у Steam!"
    )
    prices = " / ".join(p for p in (uah(deal.new_price), deal.price_usd) if p)

    lines = [f"{marker} {_game_link(deal)} {keycaps(deal.discount)}", "", headline]
    if deal.description:
        lines += ["", escape(deal.description)]
    lines += ["", f"Забираємо гру за: <b>{prices}</b> <s>{uah(deal.old_price)}</s>"]
    if deal.positive:
        lines.append(f"⭐ {deal.positive}% позитивних відгуків ({deal.reviews:,})".replace(",", " "))
    if deal.is_record:
        lines.append("📉 Найнижча ціна за всю історію гри")
    if channel:
        lines += ["", channel]
    return "\n".join(lines)


def digest_caption(deals: list[Deal], day: date, part: int, parts: int,
                   channel: str | None = None, max_chars: int = CAPTION_LIMIT) -> tuple[str, list[Deal]]:
    """Caption for one digest message; returns it and the deals that fit in it."""
    title = f"⚡️ ЗНИЖКИ НА {human_date(day).upper()}"
    if parts > 1:
        title += f" • {part}/{parts}"
    head = [title, ""]
    legend = ["", f"{RECORD} — рекорд  {REGULAR} — звичайна", "🔥 — Беру  🤷‍♂️ — Нічого цікавого"]
    if channel:
        legend += ["", channel]

    rows: list[str] = []
    used: list[Deal] = []
    budget = max_chars - tg_len("\n".join(head + legend))
    for d in deals:
        mark = RECORD if d.is_record else REGULAR
        price = uah(d.new_price)
        visible = tg_len(f"{mark} {d.title} {keycaps(d.discount)} {price}") + 1
        if budget - visible < 0:
            break
        rows.append(f"{mark} {_game_link(d)} {keycaps(d.discount)} {price}")
        used.append(d)
        budget -= visible
    return "\n".join(head + rows + legend), used


def split_digest(deals: list[Deal], day: date, max_parts: int,
                 channel: str | None = None) -> list[tuple[str, list[Deal]]]:
    """Split deals into up to max_parts captions that each fit Telegram's limit."""
    # First pass to know how many parts we need, second to number them right.
    chunks: list[list[Deal]] = []
    rest = deals
    while rest and len(chunks) < max_parts:
        _, used = digest_caption(rest, day, 1, max_parts, channel)
        if not used:
            break
        chunks.append(used)
        rest = rest[len(used):]
    return [digest_caption(c, day, i + 1, len(chunks), channel) for i, c in enumerate(chunks)]


def format_top(deals: list[Deal], limit: int = 10) -> str:
    if not deals:
        return "Зараз немає знижок, що проходять фільтр 🤷"
    rows = ["🏆 <b>Топ знижок Steam зараз</b>", ""]
    for i, d in enumerate(deals[:limit], 1):
        mark = RECORD if d.is_record else REGULAR
        rows.append(f"{i}. {mark} {_game_link(d)} — <b>{uah(d.new_price)}</b> (−{d.discount}%)")
    return "\n".join(rows)
