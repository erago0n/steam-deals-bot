"""Channel avatar in the same style as the digest cover.

Run:  python -m tools.avatar   -> writes preview/avatar_*.png (1024x1024, circle-safe)
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from bot import image as cover
from bot.image import oswald, neon_text, NEON_PINK, TOP_GREEN, BOTTOM_PURPLE
from bot.sources import fetch_deals, new_session
from bot.storage import PostedDeals

S = 1024
OUT = Path("preview")


def wall(covers: list[Image.Image]) -> Image.Image:
    old = cover.W, cover.H
    cover.W = cover.H = S
    try:
        w = cover.game_wall(covers)
        top = cover.edge_glow(TOP_GREEN, from_top=True, reach=0.5, strength=190)
        bottom = cover.edge_glow(BOTTOM_PURPLE, from_top=False, reach=0.55, strength=210)
    finally:
        cover.W, cover.H = old
    w = ImageEnhance.Brightness(w).enhance(0.85).convert("RGBA")
    shade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shade).ellipse((140, 140, S - 140, S - 140), fill=(0, 0, 0, 185))
    w.alpha_composite(shade.filter(ImageFilter.GaussianBlur(70)))
    w.alpha_composite(top)
    w.alpha_composite(bottom)
    return w


def silver_text(canvas: Image.Image, center: tuple[int, int], text: str, size: int) -> tuple[int, int, int, int]:
    fnt = oswald(size, "Bold")
    d = ImageDraw.Draw(canvas)
    l, t, r, b = d.textbbox((0, 0), text, font=fnt)
    w, h = r - l, b - t
    x0, y0 = center[0] - w // 2, center[1] - h // 2
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).text((x0 - l, y0 - t), text, font=fnt, fill=255)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * 0.9)))
    canvas.alpha_composite(shadow, (6, 10))
    grad = Image.new("RGB", (1, h))
    for yy in range(h):
        k = yy / max(1, h - 1)
        shade = 240 - 100 * k + (25 if 0.42 < k < 0.5 else 0)
        grad.putpixel((0, yy), (int(shade), int(shade), int(shade + 6)))
    fill = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    fill.paste(grad.resize((w, h)), (x0, y0))
    fill.putalpha(mask)
    canvas.alpha_composite(fill)
    return x0, y0, x0 + w, y0 + h


def neon_ring(canvas: Image.Image, color: tuple, inset: int = 40, width: int = 10) -> None:
    for radius, alpha in ((26, 255), (12, 255)):
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse((inset, inset, S - inset, S - inset), outline=(*color, alpha), width=width + 6)
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius)))
    core = tuple(min(255, c + 70) for c in color)
    ImageDraw.Draw(canvas).ellipse((inset, inset, S - inset, S - inset), outline=(*core, 255), width=width)


def variant_name(base: Image.Image) -> Image.Image:
    """'ЗНИЖКО' in silver over a pink neon 'МАТ'."""
    c = base.copy()
    box = silver_text(c, (S // 2, S // 2 - 95), "ЗНИЖКО", 230)
    neon_text(c, (S // 2, box[3] + 115), "МАТ", oswald(190, "Bold"), NEON_PINK)
    return c


def variant_percent(base: Image.Image) -> Image.Image:
    """Huge silver '%' inside a pink neon ring, small name under it."""
    c = base.copy()
    neon_ring(c, NEON_PINK)
    box = silver_text(c, (S // 2, S // 2 - 40), "%", 520)
    neon_text(c, (S // 2, box[3] + 75), "ЗНИЖКОМАТ", oswald(86, "Bold"), NEON_PINK)
    return c


def variant_ring(base: Image.Image) -> Image.Image:
    """Name variant + neon ring around the circle."""
    c = variant_name(base)
    neon_ring(c, NEON_PINK, inset=34, width=8)
    return c


def gradient_ring(canvas: Image.Image, inset: int = 36, width: int = 12) -> None:
    """Neon ring that goes from green at the top to purple at the bottom."""
    ring = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(ring).ellipse((inset, inset, S - inset, S - inset), outline=255, width=width)
    colors = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        colors.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(TOP_GREEN, BOTTOM_PURPLE)))
    colors = colors.resize((S, S))
    for radius in (26, 12, 0):
        layer = colors.convert("RGBA")
        layer.putalpha(ring.filter(ImageFilter.GaussianBlur(radius)) if radius else ring)
        canvas.alpha_composite(layer)


def plain_base() -> Image.Image:
    """Dark background with just the green/purple glows (no game wall)."""
    old = cover.W, cover.H
    cover.W = cover.H = S
    try:
        base = Image.new("RGBA", (S, S), (10, 8, 22, 255))
        base.alpha_composite(cover.edge_glow(TOP_GREEN, from_top=True, reach=0.6, strength=200))
        base.alpha_composite(cover.edge_glow(BOTTOM_PURPLE, from_top=False, reach=0.65, strength=220))
    finally:
        cover.W, cover.H = old
    return base


def variant_monogram(base: Image.Image) -> Image.Image:
    """Huge silver 'З' in a pink neon ring, name under it."""
    c = base.copy()
    neon_ring(c, NEON_PINK)
    box = silver_text(c, (S // 2, S // 2 - 50), "З", 560)
    neon_text(c, (S // 2, box[3] + 70), "ЗНИЖКОМАТ", oswald(80, "Bold"), NEON_PINK)
    return c


def variant_minus(base: Image.Image) -> Image.Image:
    """Price-tag style '−90%' in silver with the name in pink neon."""
    c = base.copy()
    box = silver_text(c, (S // 2, S // 2 - 70), "−90%", 330)
    neon_text(c, (S // 2, box[3] + 95), "ЗНИЖКОМАТ", oswald(110, "Bold"), NEON_PINK)
    return c


def variant_swap(base: Image.Image) -> Image.Image:
    """Pink neon 'ЗНИЖКО' over silver 'МАТ', gradient ring."""
    c = base.copy()
    gradient_ring(c)
    neon_text(c, (S // 2, S // 2 - 110), "ЗНИЖКО", oswald(210, "Bold"), NEON_PINK)
    silver_text(c, (S // 2, S // 2 + 140), "МАТ", 240)
    return c


def variant_gradient_percent(base: Image.Image) -> Image.Image:
    """Silver '%' in a green-to-purple neon ring."""
    c = base.copy()
    gradient_ring(c)
    box = silver_text(c, (S // 2, S // 2 - 40), "%", 520)
    neon_text(c, (S // 2, box[3] + 75), "ЗНИЖКОМАТ", oswald(86, "Bold"), NEON_PINK)
    return c


ICONS = Path("assets/icons")


def platform_badges(canvas: Image.Image, center_y: int, names=("steam", "playstation", "epicgames"),
                    badge: int = 132, gap: int = 44, ring_color: tuple = NEON_PINK) -> None:
    """Row of round badges with white platform logos and a thin neon outline."""
    total = len(names) * badge + (len(names) - 1) * gap
    x = S // 2 - total // 2
    for name in names:
        box = (x, center_y - badge // 2, x + badge, center_y + badge // 2)
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse(box, outline=(*ring_color, 255), width=8)
        canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(canvas)
        d.ellipse(box, fill=(14, 10, 28, 235), outline=(*ring_color, 255), width=4)
        icon = Image.open(ICONS / f"{name}.png").convert("RGBA")
        size = int(badge * 0.56)
        icon = icon.resize((size, size), Image.LANCZOS)
        canvas.alpha_composite(icon, (x + (badge - size) // 2, center_y - size // 2))
        x += badge + gap


def variant_ring_platforms(base: Image.Image) -> Image.Image:
    """Chosen design (ЗНИЖКО/МАТ + neon ring) with Steam / PlayStation / Epic badges at the bottom."""
    c = base.copy()
    box = silver_text(c, (S // 2, S // 2 - 190), "ЗНИЖКО", 220)
    neon_text(c, (S // 2, box[3] + 100), "МАТ", oswald(175, "Bold"), NEON_PINK)
    platform_badges(c, 785)
    neon_ring(c, NEON_PINK, inset=34, width=8)
    return c


def save_with_preview(name: str, img: Image.Image) -> None:
    img = img.convert("RGB")
    img.save(OUT / f"avatar_{name}.png")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S, S), fill=255)
    circle = Image.new("RGB", (S, S), (24, 24, 32))
    circle.paste(img, (0, 0), mask)
    circle.resize((320, 320), Image.LANCZOS).save(OUT / f"avatar_{name}_circle.png")


def contact_sheet(names: list[str], path: Path, cols: int = 3) -> None:
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 340 + 20, rows * 340 + 20), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for i, name in enumerate(names):
        x, y = 20 + (i % cols) * 340, 20 + (i // cols) * 340
        sheet.paste(Image.open(OUT / f"avatar_{name}_circle.png"), (x, y))
        d.text((x + 4, y + 2), str(i + 4), font=oswald(40, "Bold"), fill=(255, 255, 255))
    sheet.save(path)


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    store = PostedDeals("data/deals.db")
    deals = await fetch_deals(store, min_discount=50, min_reviews=5000, min_positive=70, max_scan=400)
    async with new_session() as session:
        imgs = await asyncio.gather(*(cover._download(session, d.image) for d in deals[:40]))
    base = wall([i for i in imgs if i is not None])
    plain = plain_base()
    variants = [
        ("monogram", variant_monogram(base)),
        ("minus", variant_minus(base)),
        ("swap", variant_swap(base)),
        ("gradient_percent", variant_gradient_percent(base)),
        ("plain_ring", variant_ring(plain)),
        ("plain_percent", variant_gradient_percent(plain)),
    ]
    for name, img in variants:
        save_with_preview(name, img)
    contact_sheet([n for n, _ in variants], OUT / "avatar_options_more.png")
    print("saved", [n for n, _ in variants])


if __name__ == "__main__":
    asyncio.run(main())
