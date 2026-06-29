#!/usr/bin/env bash
#
# Baut aus dem mailarc-Quellbaum ein macOS-Installationspaket:
#   1. isoliertes Build-venv (PyInstaller + Pillow + Laufzeit-Deps)
#   2. Assets (App-Icon .icns, DMG-Hintergrund @1x/@2x → .tiff)
#   3. eigenständige Binary via PyInstaller (--onedir)
#   4. Komponenten-.pkg (pkgbuild) + signierbares Installer-.pkg (productbuild)
#   5. professionelle .dmg (create-dmg) mit generiertem Hintergrund & Volume-Icon
#
# Ergebnis:  dist/macos/mailarc-<version>.pkg  und  .../mailarc-<version>.dmg
#
# Voraussetzungen: macOS, create-dmg (brew install create-dmg).
# Python-Override:  PYTHON=/pfad/zu/python3.12 ./build.sh
#                   (PyInstaller hinkt neuen Python-Versionen teils hinterher.)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

# --- Konstanten -------------------------------------------------------------
APP_NAME="mailarc"
IDENTIFIER="de.microtronix.mailarc"
PYTHON="${PYTHON:-python3}"
VERSION="$(sed -n -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' pyproject.toml | head -1)"
[ -n "$VERSION" ] || { echo "Version nicht aus pyproject.toml lesbar"; exit 1; }

BUILD="$ROOT/build/macos"
DIST="$ROOT/dist/macos"
ASSETS="$HERE/assets"
VENV="$BUILD/venv"

echo "==> mailarc $VERSION – macOS-Paket bauen"
command -v create-dmg >/dev/null || { echo "create-dmg fehlt: brew install create-dmg"; exit 1; }

rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD" "$DIST" "$ASSETS"

# --- 1. Build-venv ----------------------------------------------------------
echo "==> [1/5] Build-Umgebung einrichten ($PYTHON)"
"$PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet pyinstaller pillow

# Laufzeit-Abhängigkeiten aus pyproject.toml lesen (bash-3.2-kompatibel)
DEPS=()
while IFS= read -r line; do
  [ -n "$line" ] && DEPS+=("$line")
done < <("$PY" - "$ROOT/pyproject.toml" <<'PYEOF'
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
print("\n".join(data["project"]["dependencies"]))
PYEOF
)
"$PY" -m pip install --quiet "${DEPS[@]}"

# --- 2. Assets --------------------------------------------------------------
echo "==> [2/5] Icon & DMG-Hintergrund erzeugen"
( cd "$HERE" && "$PY" make_icon.py "$ASSETS/AppIcon.icns" )
( cd "$HERE" && "$PY" make_background.py "$ASSETS" "$VERSION" )
tiffutil -cathidpicheck \
  "$ASSETS/dmg-background.png" "$ASSETS/dmg-background@2x.png" \
  -out "$ASSETS/dmg-background.tiff" >/dev/null

# --- 3. PyInstaller ---------------------------------------------------------
echo "==> [3/5] Eigenständige Binary bauen (PyInstaller)"
# Saubere Quell-Kopie (nur das app-Paket). Wichtig: NICHT den ganzen Quellbaum
# auf den Pfad legen – ein dort liegendes *.egg-info eines früheren editable-
# Installs würde sonst mitgebündelt, und importlib.metadata meldete dessen
# (veraltete) Version statt des Fallbacks aus app/__init__.py.
SRC="$BUILD/src"
mkdir -p "$SRC"
cp -R "$ROOT/app" "$SRC/app"

"$VENV/bin/pyinstaller" --noconfirm --clean \
  --name "$APP_NAME" \
  --onedir --console \
  --paths "$SRC" \
  --collect-submodules app \
  --collect-all elasticsearch \
  --collect-data docx \
  --distpath "$BUILD/pyi" \
  --workpath "$BUILD/pyi-work" \
  --specpath "$BUILD" \
  "$HERE/entry.py"

# --- 4. .pkg ----------------------------------------------------------------
echo "==> [4/5] Installationspaket schnüren (pkgbuild + productbuild)"
PKGROOT="$BUILD/pkgroot"
mkdir -p "$PKGROOT/usr/local/$APP_NAME"
cp -R "$BUILD/pyi/$APP_NAME/." "$PKGROOT/usr/local/$APP_NAME/"

SCRIPTS="$BUILD/scripts"
mkdir -p "$SCRIPTS"
cp "$HERE/scripts/postinstall" "$SCRIPTS/postinstall"
chmod +x "$SCRIPTS/postinstall"

pkgbuild \
  --root "$PKGROOT" \
  --identifier "$IDENTIFIER" \
  --version "$VERSION" \
  --scripts "$SCRIPTS" \
  --install-location / \
  "$BUILD/${APP_NAME}-component.pkg"

sed "s/__VERSION__/$VERSION/g" "$HERE/distribution.xml" > "$BUILD/distribution.xml"
FINAL_PKG="$DIST/${APP_NAME}-${VERSION}.pkg"
productbuild \
  --distribution "$BUILD/distribution.xml" \
  --resources "$HERE/resources" \
  --package-path "$BUILD" \
  "$FINAL_PKG"

# --- 5. .dmg ----------------------------------------------------------------
echo "==> [5/5] DMG erstellen (create-dmg)"
DMG_SRC="$BUILD/dmg-src"
mkdir -p "$DMG_SRC"
cp "$FINAL_PKG" "$DMG_SRC/"
FINAL_DMG="$DIST/${APP_NAME}-${VERSION}.dmg"
rm -f "$FINAL_DMG"

create-dmg \
  --volname "$APP_NAME $VERSION" \
  --volicon "$ASSETS/AppIcon.icns" \
  --background "$ASSETS/dmg-background.tiff" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 128 \
  --text-size 13 \
  --icon "${APP_NAME}-${VERSION}.pkg" 300 248 \
  --hide-extension "${APP_NAME}-${VERSION}.pkg" \
  --no-internet-enable \
  "$FINAL_DMG" \
  "$DMG_SRC"

echo
echo "==> Fertig:"
echo "    $FINAL_PKG"
echo "    $FINAL_DMG"
