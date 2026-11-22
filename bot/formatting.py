"""Turns a Deal into a Telegram message (HTML parse mode)."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from .sources import Deal

CURRENCY_SIGNS = {"USD": "$", "EUR": "€", "GBP": "£", "UAH": "₴"}


def money(amount: float, currency: str) -> str:
    sign = CURRENCY_SIGNS.get(currency)
    value = f"{amount:.2f}"
    return f"{sign}{value}" if sign else f"{value} {currency}"


def format_deal(deal: Deal) -> str:
    fire = "🔥🔥🔥" if deal.discount >= 80 else "🔥🔥" if deal.discount >= 60 else "🔥"
    lines = [
        f"{fire} <b>{escape(deal.title)}</b>",
        "",
        f"💸 <s>{money(deal.old_price, deal.currency)}</s> → "
        f"<b>{money(deal.new_price, deal.currency)}</b>  (−{deal.discount}%)",
    ]
    if deal.rating:
        lines.append(f"⭐ {escape(deal.rating)}")
    if deal.expires_at:
        until = datetime.fromtimestamp(deal.expires_at, tz=timezone.utc).strftime("%d.%m")
        lines.append(f"⏳ Знижка до {until}")
    lines += ["", f'🛒 <a href="{deal.url}">Купити в Steam</a>']
    return "\n".join(lines)


def format_top(deals: list[Deal], limit: int = 10) -> str:
    if not deals:
        return "Зараз немає знижок, що проходять фільтр 🤷"
    rows = ["🏆 <b>Топ знижок Steam зараз</b>", ""]
    for i, d in enumerate(deals[:limit], 1):
        rows.append(
            f'{i}. <a href="{d.url}">{escape(d.title)}</a> — '
            f"<b>{money(d.new_price, d.currency)}</b> (−{d.discount}%)"
        )
    return "\n".join(rows)
