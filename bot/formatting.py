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
REGULAR = "🔥"

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


def digest_caption(deals: list[Deal], day: date, channel: str | None = None,
                   max_chars: int = CAPTION_LIMIT) -> tuple[str, list[Deal]]:
    """Caption for a digest post: the game list sits in an expandable quote.

    Returns the caption and the deals that fit (photo captions are capped by Telegram).
    """
    head = [f"⚡️ <b>ЗНИЖКИ!</b> НА {human_date(day).upper()}", "", "Відкриваємо вкладку:"]
    legend = ["", "🔥 — Беру", "🤷‍♂️ — Нічого цікавого", "", f"{RECORD} — рекордна знижка"]
    if channel:
        legend += [channel]

    rows: list[str] = []
    used: list[Deal] = []
    budget = max_chars - tg_len("\n".join(head + legend))
    for d in deals:
        mark = RECORD if d.is_record else REGULAR
        price, old = uah(d.new_price), uah(d.old_price)
        visible = tg_len(f"{mark} {d.title} −{d.discount}% {old} {price}") + 1
        if budget - visible < 0:
            break
        rows.append(f"{mark} {_game_link(d)} <code>−{d.discount}%</code> <s>{old}</s> <b>{price}</b>")
        used.append(d)
        budget -= visible
    body = [f"<blockquote expandable>{chr(10).join(rows)}</blockquote>"] if rows else []
    return "\n".join(head + body + legend), used


def format_top(deals: list[Deal], limit: int = 10) -> str:
    if not deals:
        return "Зараз немає знижок, що проходять фільтр 🤷"
    rows = ["🏆 <b>Топ знижок Steam зараз</b>", ""]
    for i, d in enumerate(deals[:limit], 1):
        mark = RECORD if d.is_record else REGULAR
        rows.append(f"{i}. {mark} {_game_link(d)} — <b>{uah(d.new_price)}</b> (−{d.discount}%)")
    return "\n".join(rows)
