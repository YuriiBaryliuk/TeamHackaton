"""Generate the app icons from the logo: the dot. Run once; the PNGs are committed.

    python -m scripts.make_icons

Discreet on purpose: on a home screen it is just a berry dot on cream.
"""
from PIL import Image, ImageDraw

from app.db import BASE_DIR

OUT = BASE_DIR / "static" / "icons"
CREAM = (251, 246, 241)       # --bg
BERRY = (155, 45, 79)         # --accent
SUPERSAMPLE = 4


def icon(size: int, dot_ratio: float, rounded: bool = False) -> Image.Image:
    """Cream square with a centred berry dot. dot_ratio = dot diameter / icon size."""
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=CREAM)
    else:
        draw.rectangle((0, 0, big - 1, big - 1), fill=CREAM)
    d = big * dot_ratio
    o = (big - d) / 2
    draw.ellipse((o, o, o + d, o + d), fill=BERRY)
    return img.resize((size, size), Image.LANCZOS)


def favicon(size: int) -> Image.Image:
    """Just the dot on transparent background, for browser tabs."""
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((big * 0.06, big * 0.06, big * 0.94, big * 0.94), fill=BERRY)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192, 0.56).save(OUT / "icon-192.png")
    icon(512, 0.56).save(OUT / "icon-512.png")
    # Maskable: the OS may crop to a circle/squircle; keep the dot inside the 80% safe zone.
    icon(512, 0.42).save(OUT / "icon-maskable-512.png")
    icon(180, 0.56).convert("RGB").save(OUT / "apple-touch-icon.png")  # iOS adds its own rounding
    favicon(32).save(OUT / "favicon-32.png")
    favicon(64).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    (OUT / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<circle cx="16" cy="16" r="14" fill="#9B2D4F"/></svg>\n', encoding="utf-8")
    print(f"Icons written to {OUT.relative_to(BASE_DIR)}/")


if __name__ == "__main__":
    main()
