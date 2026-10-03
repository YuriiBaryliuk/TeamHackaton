"""Printable round QR stickers, one per point, plus an A4 PDF sheet.

    BASE_URL=https://kropka.example.com python -m scripts.make_qr            # all points with has_qr=1
    python -m scripts.make_qr krk-demo --base-url http://10.0.0.5:8000        # just one

Output: out/stickers/<id>.png (60 mm round sticker at 300 dpi) and out/stickers/sheet.pdf.
The QR code points to {BASE_URL}/p/{id}. Error correction H (30% of the code can be
damaged and it still scans) and a 4-module quiet zone, so a worn sticker still works.
"""
import argparse
import os
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from app.db import BASE_DIR, connect

OUT_DIR = BASE_DIR / "out" / "stickers"
FONT_PATH = BASE_DIR / "scripts" / "fonts" / "Nunito.ttf"

DPI = 300
STICKER_MM = 60
SIZE = round(STICKER_MM / 25.4 * DPI)   # 709 px
SUPERSAMPLE = 3                          # draw shapes/text 3x bigger, then shrink: smooth edges

INK = (43, 29, 34)            # --ink
INK_SOFT = (111, 98, 102)     # --ink-soft
ACCENT = (155, 45, 79)        # --accent
PAPER = (255, 255, 255)

LINE_1 = "Weź, jeśli potrzebujesz."
LINE_2 = "Kliknij, co zrobiłaś."

A4_PX = (2480, 3508)          # A4 at 300 dpi
SHEET_COLS, SHEET_ROWS = 3, 4


def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    try:
        f = ImageFont.truetype(str(FONT_PATH), size)
        f.set_variation_by_name(weight)
        return f
    except OSError:
        return ImageFont.load_default(size)  # fallback if the font file is missing


def centered_text(draw: ImageDraw.ImageDraw, y: float, text: str, fnt, fill, width: int) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((width - (right - left)) / 2 - left, y - (bottom - top) / 2 - top), text, font=fnt, fill=fill)


def sticker_background(point_id: str) -> Image.Image:
    """Round sticker without the QR: ring, logo, texts. Drawn big, then scaled down."""
    d = SIZE * SUPERSAMPLE
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    ring = round(d * 0.028)
    draw.ellipse((0, 0, d - 1, d - 1), fill=ACCENT)
    draw.ellipse((ring, ring, d - 1 - ring, d - 1 - ring), fill=PAPER)

    # Logo: the filled dot + "Kropka"
    word_font = font(round(d * 0.075), "ExtraBold")
    dot_r = round(d * 0.03)
    gap = round(d * 0.02)
    word_w = draw.textlength("Kropka", font=word_font)
    total = 2 * dot_r + gap + word_w
    x0 = (d - total) / 2
    y_logo = d * 0.165
    draw.ellipse((x0, y_logo - dot_r, x0 + 2 * dot_r, y_logo + dot_r), fill=ACCENT)
    left, top, right, bottom = draw.textbbox((0, 0), "Kropka", font=word_font)
    draw.text((x0 + 2 * dot_r + gap - left, y_logo - (bottom - top) / 2 - top), "Kropka", font=word_font, fill=INK)

    # Texts under the QR code
    text_font = font(round(d * 0.047), "Bold")
    centered_text(draw, d * 0.795, LINE_1, text_font, INK, d)
    centered_text(draw, d * 0.855, LINE_2, text_font, INK, d)
    centered_text(draw, d * 0.925, point_id, font(round(d * 0.032), "SemiBold"), INK_SOFT, d)

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def draw_qr(img: Image.Image, url: str) -> None:
    """Draw the QR code with whole-pixel modules (crisp for scanners), centred."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()                 # includes the 4-module quiet zone
    n = len(matrix)
    module = int(SIZE * 0.48 // n)           # QR takes ~48% of the sticker width
    side = module * n
    x0 = (SIZE - side) // 2
    y0 = round(SIZE * 0.50 - side / 2)
    draw = ImageDraw.Draw(img)
    draw.rectangle((x0, y0, x0 + side - 1, y0 + side - 1), fill=PAPER)
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                draw.rectangle((x0 + c * module, y0 + r * module,
                                x0 + (c + 1) * module - 1, y0 + (r + 1) * module - 1), fill=INK)


def make_sticker(point_id: str, base_url: str) -> Image.Image:
    img = sticker_background(point_id)
    draw_qr(img, f"{base_url}/p/{point_id}")
    return img


def make_sheets(stickers: list[Image.Image]) -> list[Image.Image]:
    """A4 pages, 3 x 4 stickers each, with a thin grey cutting circle."""
    per_page = SHEET_COLS * SHEET_ROWS
    gap_x = (A4_PX[0] - SHEET_COLS * SIZE) // (SHEET_COLS + 1)
    gap_y = (A4_PX[1] - SHEET_ROWS * SIZE) // (SHEET_ROWS + 1)
    pages = []
    for start in range(0, len(stickers), per_page):
        page = Image.new("RGB", A4_PX, PAPER)
        draw = ImageDraw.Draw(page)
        for i, s in enumerate(stickers[start:start + per_page]):
            col, row = i % SHEET_COLS, i // SHEET_COLS
            x = gap_x + col * (SIZE + gap_x)
            y = gap_y + row * (SIZE + gap_y)
            draw.ellipse((x - 6, y - 6, x + SIZE + 5, y + SIZE + 5), outline=(200, 200, 200), width=2)
            page.paste(s, (x, y), s)
        pages.append(page)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate printable Kropka QR stickers.")
    parser.add_argument("ids", nargs="*", help="point ids (default: all points with has_qr=1)")
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL"), help="public URL of the app (or env BASE_URL)")
    args = parser.parse_args()

    base_url = (args.base_url or "http://localhost:8000").rstrip("/")
    if not args.base_url:
        print("WARNING: BASE_URL not set, using http://localhost:8000. A phone cannot open that: "
              "set BASE_URL to your public or LAN address before printing.")

    conn = connect()
    if args.ids:
        known = {r[0] for r in conn.execute("SELECT id FROM points")}
        unknown = [i for i in args.ids if i not in known]
        if unknown:
            print(f"Unknown point ids: {unknown}")
            return 1
        ids = args.ids
    else:
        ids = [r[0] for r in conn.execute("SELECT id FROM points WHERE has_qr = 1 ORDER BY id")]
    if not ids:
        print("No points to print. Run `python -m scripts.seed_points` first.")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stickers = []
    for point_id in ids:
        img = make_sticker(point_id, base_url)
        img.save(OUT_DIR / f"{point_id}.png", dpi=(DPI, DPI))
        stickers.append(img)

    pages = make_sheets(stickers)
    pages[0].save(OUT_DIR / "sheet.pdf", "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
    print(f"{len(ids)} stickers -> {OUT_DIR.relative_to(BASE_DIR)}/ (PNG each, sheet.pdf with {len(pages)} page(s))")
    print(f"QR target: {base_url}/p/<id>  ({STICKER_MM} mm at {DPI} dpi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
