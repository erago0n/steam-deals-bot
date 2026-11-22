"""Deal sources: Steam Store specials + CheapShark (Steam-only deals).

Both APIs are public and need no key. Every source returns a list of `Deal`
objects with the same shape, so adding a new store later (PS Store, GOG...)
only means writing one more fetch function.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

USER_AGENT = "SteamDealsBot/1.0 (open-source Telegram deals bot)"
STEAM_SPECIALS_URL = "https://store.steampowered.com/api/featuredcategories"
CHEAPSHARK_DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"


@dataclass(frozen=True)
class Deal:
    app_id: str
    title: str
    old_price: float
    new_price: float
    discount: int  # percent, 0-100
    currency: str
    url: str
    image: str | None = None
    rating: str | None = None  # e.g. "Very Positive (92%)"
    expires_at: int | None = None  # unix timestamp

    @property
    def key(self) -> str:
        """Identity used for de-duplication: same game at same price = same deal."""
        return f"{self.app_id}:{self.new_price:.2f}"


def _steam_url(app_id: str) -> str:
    return f"https://store.steampowered.com/app/{app_id}/"


async def fetch_steam_specials(session: aiohttp.ClientSession, country: str = "us") -> list[Deal]:
    params = {"cc": country, "l": "english"}
    async with session.get(STEAM_SPECIALS_URL, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)

    deals: list[Deal] = []
    for item in data.get("specials", {}).get("items", []):
        if not item.get("discounted"):
            continue
        app_id = str(item["id"])
        deals.append(
            Deal(
                app_id=app_id,
                title=item["name"],
                old_price=item["original_price"] / 100,
                new_price=item["final_price"] / 100,
                discount=int(item["discount_percent"]),
                currency=item.get("currency", "USD"),
                url=_steam_url(app_id),
                image=item.get("header_image") or item.get("large_capsule_image"),
                expires_at=item.get("discount_expiration"),
            )
        )
    return deals


async def fetch_cheapshark(session: aiohttp.ClientSession, page_size: int = 60) -> list[Deal]:
    params = {
        "storeID": "1",  # 1 = Steam
        "onSale": "1",
        "sortBy": "Deal Rating",
        "pageSize": str(page_size),
    }
    async with session.get(CHEAPSHARK_DEALS_URL, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)

    deals: list[Deal] = []
    for item in data:
        app_id = item.get("steamAppID")
        if not app_id:
            continue
        rating = None
        if item.get("steamRatingText"):
            rating = f"{item['steamRatingText']} ({item.get('steamRatingPercent', '?')}%)"
        deals.append(
            Deal(
                app_id=str(app_id),
                title=item["title"],
                old_price=float(item["normalPrice"]),
                new_price=float(item["salePrice"]),
                discount=round(float(item["savings"])),
                currency="USD",
                url=_steam_url(app_id),
                image=f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
                rating=rating,
            )
        )
    return deals


async def fetch_all_deals(country: str = "us") -> list[Deal]:
    """Fetch every source, skip any that fail, merge by app_id (keep the bigger discount)."""
    headers = {"User-Agent": USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=20)
    merged: dict[str, Deal] = {}

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for name, fetch in (
            ("steam", lambda: fetch_steam_specials(session, country)),
            ("cheapshark", lambda: fetch_cheapshark(session)),
        ):
            try:
                for deal in await fetch():
                    current = merged.get(deal.app_id)
                    if current is None or deal.discount > current.discount:
                        # keep rating from CheapShark if Steam entry wins
                        if current and current.rating and not deal.rating:
                            deal = Deal(**{**deal.__dict__, "rating": current.rating})
                        merged[deal.app_id] = deal
            except Exception as exc:  # one broken source must not stop the bot
                log.warning("Source %s failed: %s", name, exc)

    return sorted(merged.values(), key=lambda d: d.discount, reverse=True)
