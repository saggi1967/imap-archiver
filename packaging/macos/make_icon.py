"""Erzeugt AppIcon.icns aus dem Marken-Icon (für das DMG-Volume-Icon).

Aufruf:  python make_icon.py <ziel.icns>
"""

import os
import subprocess
import sys
import tempfile

from PIL import Image

from brand import draw_app_icon

# (Punktgröße, Scale) – die von iconutil erwarteten Iconset-Varianten
_SPECS = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
          (256, 1), (256, 2), (512, 1), (512, 2)]


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "AppIcon.icns"
    base = draw_app_icon(1024)

    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "AppIcon.iconset")
        os.makedirs(iconset)
        for pt, scale in _SPECS:
            px = pt * scale
            suffix = "@2x" if scale == 2 else ""
            name = f"icon_{pt}x{pt}{suffix}.png"
            base.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, name))
        subprocess.run(["iconutil", "-c", "icns", "-o", out, iconset], check=True)

    print(f"  ✓ Icon erzeugt: {out}")


if __name__ == "__main__":
    main()
