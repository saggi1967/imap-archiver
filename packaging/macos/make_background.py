"""Erzeugt den DMG-Hintergrund (1x + @2x PNG) für ein professionelles Layout.

Aufruf:  python make_background.py <asset-verzeichnis> [version]

Das Layout ist auf ein 600x400-Fenster ausgelegt; die Position ICON_POS muss
mit dem ``create-dmg --icon``-Aufruf in build.sh übereinstimmen.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

from brand import (
    CYAN,
    DIM,
    NAVY_BOTTOM,
    NAVY_TOP,
    WHITE,
    draw_app_icon,
    load_font,
    vertical_gradient,
)

W, H = 600, 400
ICON_POS = (300, 248)  # Finder-Position des .pkg – muss zu build.sh passen


def _centered(draw, text, font, cx, y, fill):
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)


def render(scale: int, version: str) -> Image.Image:
    w, h = W * scale, H * scale
    cx, cy = ICON_POS[0] * scale, ICON_POS[1] * scale

    img = vertical_gradient(w, h, NAVY_TOP, NAVY_BOTTOM).convert("RGBA")

    # Weicher Glow hinter der Icon-Position
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gr = 104 * scale
    ImageDraw.Draw(glow).ellipse(
        [cx - gr, cy - gr, cx + gr, cy + gr], fill=(56, 189, 248, 55)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(26 * scale))
    img = Image.alpha_composite(img, glow)

    draw = ImageDraw.Draw(img)

    # Zielring um die Icon-Position (dezent, knapp außerhalb des 128px-Icons)
    rr = 78 * scale
    draw.ellipse(
        [cx - rr, cy - rr, cx + rr, cy + rr],
        outline=(56, 189, 248, 130),
        width=max(1, round(2 * scale)),
    )

    # Dekoratives App-Icon oben links
    deco = draw_app_icon(64 * scale)
    img.alpha_composite(deco, (44 * scale, 44 * scale))

    draw = ImageDraw.Draw(img)

    # Kopfzeile
    draw.text((124 * scale, 48 * scale), "mailarc", font=load_font(50 * scale, "bold"), fill=WHITE)
    draw.text(
        (126 * scale, 108 * scale),
        "Read-only IMAP-Mailarchiv  →  SQLite  →  Elasticsearch",
        font=load_font(16 * scale, "regular"),
        fill=CYAN,
    )

    # Handlungsaufforderung unten, zentriert
    _centered(draw, "Zum Installieren doppelklicken",
              load_font(20 * scale, "bold"), w // 2, 330 * scale, WHITE)
    _centered(draw, f"Version {version}  ·  microtronix",
              load_font(13 * scale, "regular"), w // 2, 360 * scale, DIM)

    return img


def main() -> None:
    assets = sys.argv[1] if len(sys.argv) > 1 else "assets"
    version = sys.argv[2] if len(sys.argv) > 2 else "1.0.0"
    os.makedirs(assets, exist_ok=True)

    render(1, version).convert("RGB").save(os.path.join(assets, "dmg-background.png"))
    render(2, version).convert("RGB").save(os.path.join(assets, "dmg-background@2x.png"))
    print(f"  ✓ Hintergrund erzeugt: {assets}/dmg-background.png (+ @2x)")


if __name__ == "__main__":
    main()
