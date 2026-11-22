"""Digest cover image: a hero banner for the best deal plus a grid of 8 more."""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import date
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .formatting import human_date, uah
from .sources import Deal, new_session

log = logging.getLogger(__name__)

W = 1280
PAD = 48
GAP = 18
HEADER_H = 172
HERO_H = 380
COLS = 4
CARD_W = (W - 2 * PAD - (COLS - 1) * GAP) // COLS
CARD_H = CARD_W * 215 // 460 + 56  # cover + price strip
FOOTER_H = 90

BG_TOP = (10, 14, 34)
BG_BOTTOM = (40, 16, 72)
TEXT = (245, 247, 252)
MUTED = (165, 172, 195)
NEON = (57, 255, 136)
NEON_DARK = (8, 40, 24)
ORANGE = (255, 166, 0)
CARD = (22, 26, 48)

FONT_CANDIDATES = {
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
}


def font(size: int, weight: str = "bold"):
    for path in FONT_CANDIDATES[weight]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


# ---------- drawing helpers ----------

def vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return grad.resize((w, h))


def glow(canvas: Image.Image, center: tuple[int, int], radius: int, color: tuple, strength: int = 90) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        fill=(*color, strength),
    )
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius // 2)))


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    ratio = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def fade_right(img: Image.Image, color: tuple, start: float = 0.55) -> Image.Image:
    """Fade the right part of an image into a solid colour (for text over the hero)."""
    w, h = img.size
    mask = Image.new("L", (w, 1))
    for x in range(w):
        t = max(0.0, (x / w - start) / (1 - start))
        mask.putpixel((x, 0), round(255 * min(1.0, t * 1.15)))
    overlay = Image.new("RGB", (w, h), color)
    return Image.composite(overlay, img.convert("RGB"), mask.resize((w, h)))


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt, fill, color=TEXT,
         anchor_right: bool = False, pad=(16, 8)) -> tuple[int, int, int, int]:
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    w, h = r - l + 2 * pad[0], b - t + 2 * pad[1]
    x, y = xy
    if anchor_right:
        x -= w
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill)
    draw.text((x + pad[0] - l, y + pad[1] - t), text, font=fnt, fill=color)
    return x, y, x + w, y + h


def strike(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt, fill) -> None:
    draw.text(xy, text, font=fnt, fill=fill)
    l, t, r, b = draw.textbbox(xy, text, font=fnt)
    mid = (t + b) // 2
    draw.line((l, mid, r, mid), fill=fill, width=3)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int, max_lines: int = 2) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and " ".join(lines) != text:
        while draw.textlength(lines[-1] + "…", font=fnt) > max_w and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


# ---------- layout ----------

def _hero(canvas: Image.Image, deal: Deal, cover: Image.Image | None, y: int) -> None:
    w, h = W - 2 * PAD, HERO_H
    base = cover_fit(cover, w, h) if cover else Image.new("RGB", (w, h), CARD)
    base = fade_right(base, CARD, start=0.45)
    canvas.alpha_composite(rounded(base, 28), (PAD, y))
    d = ImageDraw.Draw(canvas, "RGBA")

    x0 = PAD + int(w * 0.58)
    tx = x0 + 10
    if deal.is_record:
        pill(d, (tx, y + 30), "РЕКОРДНА ЦІНА", font(22), NEON, color=NEON_DARK)
    title_f = font(36)
    ty = y + 82
    for line in wrap(d, deal.title, title_f, W - PAD - tx - 30):
        d.text((tx, ty), line, font=title_f, fill=TEXT)
        ty += 44
    pill(d, (tx, ty + 12), f"−{deal.discount}%", font(50), NEON, color=NEON_DARK, pad=(22, 8))
    price_f = font(54)
    d.text((tx, ty + 100), uah(deal.new_price), font=price_f, fill=TEXT)
    pw = d.textlength(uah(deal.new_price), font=price_f)
    strike(d, (tx + pw + 22, ty + 118), uah(deal.old_price), font(28, "regular"), MUTED)
    if deal.positive:
        d.text((tx, ty + 172), f"{deal.positive}% позитивних відгуків", font=font(22, "regular"), fill=MUTED)


def _card(canvas: Image.Image, deal: Deal, cover: Image.Image | None, x: int, y: int) -> None:
    img_h = CARD_H - 56
    card = Image.new("RGB", (CARD_W, CARD_H), CARD)
    if cover:
        card.paste(cover_fit(cover, CARD_W, img_h), (0, 0))
    canvas.alpha_composite(rounded(card, 18), (x, y))
    d = ImageDraw.Draw(canvas, "RGBA")
    pill(d, (x + CARD_W - 10, y + 10), f"−{deal.discount}%", font(24), NEON if deal.is_record else ORANGE,
         color=NEON_DARK, anchor_right=True, pad=(12, 6))
    price_f = font(28)
    d.text((x + 14, y + img_h + 12), uah(deal.new_price), font=price_f, fill=TEXT)
    pw = d.textlength(uah(deal.new_price), font=price_f)
    strike(d, (x + 14 + pw + 12, y + img_h + 18), uah(deal.old_price), font(20, "regular"), MUTED)
    if deal.is_record:
        d.ellipse((x + CARD_W - 30, y + img_h + 22, x + CARD_W - 14, y + img_h + 38), fill=NEON)


def render_digest(deals: list[Deal], covers: list[Image.Image | None], day: date,
                  channel: str | None, part: int = 1, parts: int = 1, total: int | None = None) -> bytes:
    hero, grid = deals[0], deals[1:9]
    rows = (len(grid) + COLS - 1) // COLS
    height = HEADER_H + HERO_H + (GAP * 2 + rows * (CARD_H + GAP) if rows else GAP) + FOOTER_H

    canvas = vertical_gradient(W, height, BG_TOP, BG_BOTTOM).convert("RGBA")
    glow(canvas, (W - 120, 60), 260, (120, 60, 255), 110)
    glow(canvas, (140, height - 80), 240, (0, 200, 140), 70)
    d = ImageDraw.Draw(canvas, "RGBA")

    # header
    pill(d, (PAD, 40), "STEAM", font(22), (255, 255, 255), color=BG_TOP, pad=(14, 6))
    d.text((PAD, 78), "ЗНИЖКИ ДНЯ", font=font(56), fill=TEXT)
    chip = human_date(day) + (f"  •  {part}/{parts}" if parts > 1 else "")
    pill(d, (W - PAD, 52), chip, font(28), (66, 52, 120), anchor_right=True, pad=(20, 10))
    if total:
        d.text((W - PAD - d.textlength(f"{total} ігор зі знижкою", font=font(22, "regular")), 108),
               f"{total} ігор зі знижкою", font=font(22, "regular"), fill=MUTED)

    # hero + grid
    _hero(canvas, hero, covers[0], HEADER_H)
    gy = HEADER_H + HERO_H + GAP * 2
    for i, (deal, cover) in enumerate(zip(grid, covers[1:])):
        _card(canvas, deal, cover, PAD + (i % COLS) * (CARD_W + GAP), gy + (i // COLS) * (CARD_H + GAP))

    # footer
    fy = height - FOOTER_H + 22
    d.ellipse((PAD, fy + 10, PAD + 16, fy + 26), fill=NEON)
    d.text((PAD + 26, fy + 4), "рекордна ціна", font=font(24, "regular"), fill=MUTED)
    d.text((PAD + 230, fy + 4), "Повний список із посиланнями — під фото", font=font(24, "regular"), fill=MUTED)
    if channel:
        d.text((W - PAD - d.textlength(channel, font=font(28)), fy), channel, font=font(28), fill=TEXT)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=90)
    return out.getvalue()


async def _download(session: aiohttp.ClientSession, url: str) -> Image.Image | None:
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return Image.open(io.BytesIO(await resp.read())).convert("RGB")
    except Exception as exc:
        log.info("Cover download failed (%s): %s", url, exc)
        return None


async def build_digest_image(deals: list[Deal], day: date, channel: str | None,
                             part: int = 1, parts: int = 1, total: int | None = None) -> bytes:
    deals = deals[:9]
    async with new_session() as session:
        urls = [deals[0].capsule] + [x.image for x in deals[1:]]
        covers = list(await asyncio.gather(*(_download(session, u) for u in urls)))
        if covers[0] is None:  # some games have no large capsule
            covers[0] = await _download(session, deals[0].image)
    return await asyncio.to_thread(render_digest, deals, covers, day, channel, part, parts, total)
