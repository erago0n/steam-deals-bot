"""Where deals come from.

- Steam store search (specials=1): every discounted game, with UAH prices and review stats.
- CheapShark: all-time lowest price, used to flag record-low deals.
- Steam appdetails: Ukrainian description and USD price for single posts.

All APIs are public and need no key.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from typing import Protocol

import aiohttp

log = logging.getLogger(__name__)

USER_AGENT = "SteamDealsBot/1.0 (open-source Telegram deals bot)"
STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
CHEAPSHARK_GAMES_URL = "https://www.cheapshark.com/api/1.0/games"


@dataclass(frozen=True)
class Deal:
    app_id: str
    title: str
    old_price: float  # UAH
    new_price: float  # UAH
    discount: int  # percent, 0-100
    url: str
    reviews: int = 0  # number of user reviews
    positive: int = 0  # % positive reviews
    rating_text: str | None = None  # e.g. "Very Positive"
    is_record: bool = False  # all-time lowest price
    price_usd: str | None = None  # e.g. "$5.99" (filled for single posts)
    description: str | None = None  # short Ukrainian description (single posts)

    @property
    def key(self) -> str:
        """Identity used for de-duplication: same game at same price = same deal."""
        return f"{self.app_id}:{self.new_price:.0f}"

    @property
    def image(self) -> str:
        return f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{self.app_id}/header.jpg"

    @property
    def capsule(self) -> str:
        """Large 616x353 capsule, nicer for the hero slot of the digest image."""
        return f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{self.app_id}/capsule_616x353.jpg"


class Cache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...


def new_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
        timeout=aiohttp.ClientTimeout(total=30),
    )


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict) -> object:
    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        return json.loads(await resp.text())


# ---------- Steam search: every discounted game ----------

_ROW_RE = re.compile(r'<a href="https://store\.steampowered\.com/app/(\d+)/.*?</a>', re.S)
_REVIEW_RE = re.compile(r"(\d+)% of the ([\d,]+) user reviews")


def _uah(text: str) -> float | None:
    digits = re.sub(r"[^\d,.]", "", text).replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return None


def parse_search_html(page: str) -> list[Deal]:
    deals: list[Deal] = []
    for m in _ROW_RE.finditer(page):
        row, app_id = m.group(0), m.group(1)
        title = re.search(r'<span class="title">(.*?)</span>', row, re.S)
        pct = re.search(r'data-discount="(\d+)"', row)
        old = re.search(r'discount_original_price">([^<]+)<', row)
        new = re.search(r'discount_final_price">([^<]+)<', row)
        if not (title and pct and old and new) or int(pct.group(1)) <= 0:
            continue
        old_p, new_p = _uah(old.group(1)), _uah(new.group(1))
        if old_p is None or new_p is None:
            continue
        reviews = positive = 0
        rating_text = None
        tip = re.search(r'search_review_summary[^"]*" data-tooltip-html="([^"]*)"', row)
        if tip:
            tip_text = html.unescape(tip.group(1))
            rating_text = tip_text.split("<br>")[0].strip() or None
            r = _REVIEW_RE.search(tip_text)
            if r:
                positive, reviews = int(r.group(1)), int(r.group(2).replace(",", ""))
        deals.append(
            Deal(
                app_id=app_id,
                title=html.unescape(title.group(1)).strip(),
                old_price=old_p,
                new_price=new_p,
                discount=int(pct.group(1)),
                url=f"https://store.steampowered.com/app/{app_id}/",
                reviews=reviews,
                positive=positive,
                rating_text=rating_text,
            )
        )
    return deals


async def fetch_steam_discounts(session: aiohttp.ClientSession, max_items: int = 2000) -> list[Deal]:
    """All discounted games (most relevant first), up to max_items."""
    found: dict[str, Deal] = {}
    start, total = 0, None
    while start < max_items and (total is None or start < total):
        params = {
            "specials": "1", "infinite": "1", "start": str(start), "count": "100",
            "cc": "ua", "l": "english", "category1": "998",  # 998 = games only
        }
        try:
            data = await _get_json(session, STEAM_SEARCH_URL, params)
        except Exception as exc:
            log.warning("Steam search page at %d failed: %s", start, exc)
            break
        total = int(data.get("total_count") or 0)
        page_html = data.get("results_html", "")
        rows = len(_ROW_RE.findall(page_html))
        if rows == 0:
            break
        for d in parse_search_html(page_html):
            found.setdefault(d.app_id, d)
        start += rows
        await asyncio.sleep(0.7)  # be polite to Steam
    log.info("Steam search: %d discounted games scanned (of %s)", len(found), total)
    return list(found.values())


# ---------- CheapShark: is it the lowest price ever? ----------

RECORD_TTL = 6 * 3600  # re-check a game's record status at most every 6 hours


async def mark_records(session: aiohttp.ClientSession, deals: list[Deal], cache: Cache,
                       max_requests: int = 40) -> list[Deal]:
    """Set is_record=True when Steam's current price equals the all-time low.

    CheapShark rate-limits hard, so this works incrementally: every run spends at most
    `max_requests` calls (stopping at the first 429) and caches what it learned, so after
    a few runs every popular game is covered. Deals are expected best-first.
    """
    budget = max_requests
    now = int(time.time())

    # 1) Steam app id -> CheapShark game id (cached forever)
    game_ids: dict[str, str] = {}
    for d in deals:
        cached = cache.get(f"cs:{d.app_id}")
        if cached is None and budget > 0:
            try:
                budget -= 1
                found = await _get_json(session, CHEAPSHARK_GAMES_URL, {"steamAppID": d.app_id})
                cached = str(found[0]["gameID"]) if found else "-"
                cache.set(f"cs:{d.app_id}", cached)
                await asyncio.sleep(1.2)
            except aiohttp.ClientResponseError as exc:
                if exc.status == 429:
                    log.info("CheapShark rate limit hit, continuing next run")
                    budget = 0
                continue
            except Exception as exc:
                log.info("CheapShark lookup failed for %s: %s", d.title, exc)
                continue
        if cached and cached != "-":
            game_ids[d.app_id] = cached

    # 2) record status per deal key, refreshed when stale
    def cached_status(d: Deal) -> bool | None:
        raw = cache.get(f"rec:{d.key}")
        if raw is None:
            return None
        flag, _, ts = raw.partition(":")
        return flag == "1" if now - int(ts or 0) < RECORD_TTL else None

    stale = [d for d in deals if d.app_id in game_ids and cached_status(d) is None]
    for i in range(0, len(stale), 25):  # API accepts up to 25 ids per call
        if budget <= 0:
            break
        chunk = {game_ids[d.app_id]: d for d in stale[i : i + 25]}
        try:
            budget -= 1
            data = await _get_json(session, CHEAPSHARK_GAMES_URL, {"ids": ",".join(chunk)})
            await asyncio.sleep(1.2)
        except aiohttp.ClientResponseError as exc:
            if exc.status == 429:
                log.info("CheapShark rate limit hit, continuing next run")
                break
            continue
        except Exception as exc:
            log.warning("Price history lookup failed: %s", exc)
            continue
        for gid, info in data.items():
            d = chunk.get(gid)
            if d is None:
                continue
            lowest = float(info["cheapestPriceEver"]["price"])
            steam = [float(x["price"]) for x in info.get("deals", []) if x.get("storeID") == "1"]
            is_rec = bool(steam) and steam[0] <= lowest + 0.01
            cache.set(f"rec:{d.key}", f"{int(is_rec)}:{now}")

    return [replace(d, is_record=bool(cached_status(d))) for d in deals]


# ---------- Steam appdetails: description + USD price ----------

def _short_description(raw: str, limit: int = 220) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    # Take whole sentences until the text is informative (~80+ chars) but still short.
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s", text):
        if out and len(out) + len(sentence) + 1 > limit:
            break
        out = f"{out} {sentence}".strip()
        if len(out) >= 80:
            break
    if len(out) > limit:
        out = out[: limit - 1].rsplit(" ", 1)[0] + "…"
    return out


async def enrich(session: aiohttp.ClientSession, deal: Deal) -> Deal:
    """Add the Ukrainian description and USD price (best effort)."""
    description, usd = None, None
    try:
        ua = await _get_json(session, STEAM_APPDETAILS_URL, {"appids": deal.app_id, "cc": "ua", "l": "ukrainian"})
        info = ua.get(deal.app_id, {})
        if info.get("success"):
            text = _short_description(info["data"].get("short_description", ""))
            if re.search(r"[а-яіїєґА-ЯІЇЄҐ]", text):  # skip when Steam fell back to English
                description = text
        await asyncio.sleep(0.5)
        us = await _get_json(session, STEAM_APPDETAILS_URL, {"appids": deal.app_id, "cc": "us", "filters": "price_overview"})
        price = (us.get(deal.app_id, {}).get("data") or {}).get("price_overview") or {}
        if price.get("currency") == "USD":
            usd = price.get("final_formatted")
    except Exception as exc:
        log.info("Enrich failed for %s: %s", deal.title, exc)
    return replace(deal, description=description, price_usd=usd)


async def enrich_many(deals: list[Deal]) -> list[Deal]:
    async with new_session() as session:
        out = []
        for d in deals:
            out.append(await enrich(session, d))
            await asyncio.sleep(0.5)
        return out


# ---------- everything together ----------

def is_interesting(d: Deal, min_discount: int, min_reviews: int, min_positive: int) -> bool:
    return d.discount >= min_discount and d.reviews >= min_reviews and d.positive >= min_positive


async def fetch_deals(cache: Cache, *, min_discount: int, min_reviews: int, min_positive: int,
                      max_scan: int = 2000) -> list[Deal]:
    """Interesting discounted games, record lows flagged, best first."""
    async with new_session() as session:
        all_deals = await fetch_steam_discounts(session, max_scan)
        picked = [d for d in all_deals if is_interesting(d, min_discount, min_reviews, min_positive)]
        picked = await mark_records(session, picked, cache)
    log.info("Interesting deals: %d (records: %d)", len(picked), sum(d.is_record for d in picked))
    return sorted(picked, key=lambda d: (d.is_record, d.reviews), reverse=True)
