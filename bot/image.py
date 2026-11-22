"""Digest cover image: a wall of game covers, a Marvel-style "ЗНИЖКИ" title and a neon date."""
from __future__ import annotations

import asyncio
import io
import logging
import random
from datetime import date
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .sources import Deal, new_session

log = logging.getLogger(__name__)

W, H = 1280, 1280
TILE_W, TILE_H = 276, 129  # Steam header ratio 460x215
TILE_GAP = 8

MARVEL_RED = (237, 29, 36)
WHITE = (255, 255, 255)
NEON_PINK = (255, 61, 199)
TOP_GREEN = (40, 255, 140)
BOTTOM_PURPLE = (150, 60, 255)

OSWALD = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Oswald.ttf"


def oswald(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    fnt = ImageFont.truetype(str(OSWALD), size)
    try:
        fnt.set_variation_by_name(weight)
    except Exception:  # static build of the font
        pass
    return fnt


# ---------- layers ----------

def game_wall(covers: list[Image.Image]) -> Image.Image:
    """Brick-pattern wall of covers filling the whole canvas, darkened."""
    wall = Image.new("RGB", (W, H), (8, 8, 14))
    if not covers:
        return wall
    rng = random.Random(len(covers))
    pool = covers[:]
    rng.shuffle(pool)
    i = 0
    y = -TILE_H // 3
    row = 0
    while y < H:
        x = -(TILE_W // 2) * (row % 2) - TILE_W // 4
        while x < W:
            tile = pool[i % len(pool)].resize((TILE_W, TILE_H), Image.LANCZOS)
            wall.paste(tile, (x, y))
            i += 1
            x += TILE_W + TILE_GAP
        y += TILE_H + TILE_GAP
        row += 1
    wall = ImageEnhance.Color(wall).enhance(0.85)
    return ImageEnhance.Brightness(wall).enhance(0.34)


def edge_glow(color: tuple, from_top: bool, reach: float, strength: int) -> Image.Image:
    """Coloured light fading from the top or bottom edge."""
    layer = Image.new("RGBA", (W, H), (*color, 0))
    alpha = Image.new("L", (1, H))
    span = int(H * reach)
    for y in range(H):
        dist = y if from_top else H - 1 - y
        t = max(0.0, 1 - dist / span)
        alpha.putpixel((0, y), int(strength * t ** 1.6))
    layer.putalpha(alpha.resize((W, H)))
    return layer


def center_shade() -> Image.Image:
    """Dark ellipse behind the title so it reads well over busy covers."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((80, 360, W - 80, H - 360), fill=(0, 0, 0, 175))
    return layer.filter(ImageFilter.GaussianBlur(90))


def neon_text(canvas: Image.Image, center: tuple[int, int], text: str, fnt, color: tuple) -> None:
    """Text with a soft neon glow (several blurred copies under a bright core)."""
    d0 = ImageDraw.Draw(canvas)
    l, t, r, b = d0.textbbox((0, 0), text, font=fnt)
    x, y = center[0] - (r - l) // 2 - l, center[1] - (b - t) // 2 - t
    for radius, alpha in ((34, 255), (16, 255), (6, 255)):
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).text((x, y), text, font=fnt, fill=(*color, alpha))
        canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius)))
    core = tuple(min(255, c + 60) for c in color)  # whiter centre, like a neon tube
    ImageDraw.Draw(canvas).text((x, y), text, font=fnt, fill=(*core, 255))


def marvel_title(canvas: Image.Image, center: tuple[int, int], text: str) -> tuple[int, int, int, int]:
    """Big condensed Marvel-style letters with a brushed-silver (grey) gradient and a drop shadow."""
    fnt = oswald(280, "Bold")
    d = ImageDraw.Draw(canvas)
    l, t, r, b = d.textbbox((0, 0), text, font=fnt)
    w, h = r - l, b - t
    x0, y0 = center[0] - w // 2, center[1] - h // 2

    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).text((x0 - l, y0 - t), text, font=fnt, fill=255)

    # drop shadow
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.85)))
    canvas.alpha_composite(shadow, (10, 16))

    # silver gradient: light grey on top, darker grey at the bottom, with a bright band
    grad = Image.new("RGB", (1, h))
    for yy in range(h):
        k = yy / max(1, h - 1)
        shade = 235 - 95 * k
        if 0.42 < k < 0.5:  # metallic highlight line
            shade += 25
        grad.putpixel((0, yy), (int(shade), int(shade), int(shade + 6)))
    fill = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    fill.paste(grad.resize((w, h)), (x0, y0))
    fill.putalpha(mask)
    canvas.alpha_composite(fill)
    return x0, y0, x0 + w, y0 + h


def render_cover(covers: list[Image.Image], day: date, channel: str | None, count: int | None) -> bytes:
    canvas = game_wall(covers).convert("RGBA")
    canvas.alpha_composite(center_shade())
    canvas.alpha_composite(edge_glow(TOP_GREEN, from_top=True, reach=0.42, strength=170))
    canvas.alpha_composite(edge_glow(BOTTOM_PURPLE, from_top=False, reach=0.45, strength=190))

    box = marvel_title(canvas, (W // 2, H // 2 - 60), "ЗНИЖКИ")
    neon_text(canvas, (W // 2, box[3] + 95), f"{day:%d.%m.%Y}", oswald(104, "Medium"), NEON_PINK)

    d = ImageDraw.Draw(canvas)
    if count:
        sub = f"{count} популярних ігор зі знижкою".upper()
        f = oswald(34, "Regular")
        d.text((W // 2 - d.textlength(sub, font=f) // 2, box[1] - 70), sub, font=f, fill=(230, 255, 240))
    if channel:
        f = oswald(40, "Medium")
        d.text((W // 2 - d.textlength(channel, font=f) // 2, H - 92), channel, font=f, fill=WHITE)

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
                             count: int | None = None, max_covers: int = 40) -> bytes:
    async with new_session() as session:
        covers = await asyncio.gather(*(_download(session, d.image) for d in deals[:max_covers]))
    covers = [c for c in covers if c is not None]
    return await asyncio.to_thread(render_cover, covers, day, channel, count)
