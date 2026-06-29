"""Gemeinsame Marken-Bausteine für Icon- und DMG-Hintergrund-Generierung.

Farben sind vom CLI-Banner abgeleitet (cyan / bright_blue). Schriften werden
aus den macOS-Systemfonts geladen, mit Fallbacks falls eine Datei fehlt.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

# --- Markenfarben -----------------------------------------------------------
NAVY_TOP = (11, 31, 58)     # #0b1f3a  – oberer Verlaufston (Hintergrund)
NAVY_BOTTOM = (19, 49, 92)  # #13315c  – unterer Verlaufston
CYAN = (56, 189, 248)       # #38bdf8  – Akzent
BLUE = (37, 99, 235)        # #2563eb  – Icon-Verlauf unten
WHITE = (245, 248, 252)
DIM = (148, 178, 214)       # gedämpfter Text

_FONTS = {
    "regular": [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/SFNS.ttf",  # Variable Font – Bold via Variation
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ],
}


def load_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    size = max(1, int(size))
    for path in _FONTS[weight]:
        try:
            font = ImageFont.truetype(path, size)
        except OSError:
            continue
        if weight == "bold":
            try:
                font.set_variation_by_name("Bold")
            except Exception:
                pass  # nicht-variable Schrift: ist bereits die Bold-Datei
        return font
    return ImageFont.load_default()


def vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    """Vertikaler Farbverlauf von ``top`` nach ``bottom``."""
    img = Image.new("RGB", (w, h), top)
    draw = ImageDraw.Draw(img)
    span = max(1, h - 1)
    for y in range(h):
        t = y / span
        col = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=col)
    return img


def draw_app_icon(size: int) -> Image.Image:
    """Zeichnet ein App-Icon (Squircle mit Briefumschlag) als RGBA-Bild."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Verlaufs-Squircle (Big-Sur-Eckenradius ≈ 22,37 %)
    radius = round(size * 0.2237)
    grad = vertical_gradient(size, size, CYAN, BLUE).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255
    )
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)

    # Briefumschlag (weiß) – mittig
    ex0, ey0 = size * 0.22, size * 0.33
    ex1, ey1 = size * 0.78, size * 0.69
    body_r = size * 0.045
    line_w = max(2, round(size * 0.014))
    draw.rounded_rectangle([ex0, ey0, ex1, ey1], radius=body_r, fill=WHITE)

    # Umschlagklappe (V-Linien von den oberen Ecken zur Mitte)
    cx = (ex0 + ex1) / 2
    flap_y = ey0 + (ey1 - ey0) * 0.46
    inset = (ex1 - ex0) * 0.06
    draw.line(
        [(ex0 + inset, ey0 + inset * 0.4), (cx, flap_y), (ex1 - inset, ey0 + inset * 0.4)],
        fill=BLUE,
        width=line_w,
        joint="curve",
    )
    return img
