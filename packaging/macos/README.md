# macOS-Paketierung

Baut aus dem Quellbaum ein eigenständiges macOS-Installationspaket – als
`.pkg` (Installer) **und** als `.dmg` (mit professionellem, automatisch
erzeugtem Hintergrund und Volume-Icon).

## Schnellstart

```bash
brew install create-dmg          # einmalig
packaging/macos/build.sh
```

Ergebnis:

```
dist/macos/mailarc-<version>.pkg
dist/macos/mailarc-<version>.dmg
```

Die Version wird automatisch aus `pyproject.toml` gelesen.

## Was das Skript tut

1. **Build-venv** in `build/macos/venv` – installiert PyInstaller, Pillow und
   die Laufzeit-Abhängigkeiten (aus `pyproject.toml`). Das Projekt-venv bleibt
   unangetastet.
2. **Assets** – erzeugt `assets/AppIcon.icns` und den DMG-Hintergrund
   (`dmg-background.png` @1x + @2x → `dmg-background.tiff` für Retina).
   Beides wird vollständig aus Code generiert (`make_icon.py`,
   `make_background.py`, gemeinsame Marke in `brand.py`).
3. **Binary** – PyInstaller bündelt eine eigenständige `mailarc` (`--onedir`),
   inklusive eingebettetem Python; auf dem Zielrechner muss nichts vorinstalliert
   sein.
4. **.pkg** – `pkgbuild` packt die Binary nach `/usr/local/mailarc`,
   `productbuild` ergänzt Begrüßung, Lizenz und Abschluss; ein `postinstall`-Skript
   legt den Symlink `/usr/local/bin/mailarc` an **und bietet am Ende den
   Einrichtungs-Assistenten an** (siehe unten).
5. **.dmg** – `create-dmg` legt das `.pkg` mit Hintergrundbild, Fenstergröße und
   Icon-Position auf "Zum Installieren doppelklicken" aus.

## Installation (Endnutzer)

DMG öffnen → `.pkg` doppelklicken → Installer folgen. Am Ende fragt der Installer,
ob die **zentrale Konfiguration** jetzt eingerichtet werden soll. Bei „Jetzt
einrichten" startet `mailarc setup` in einem Terminal und fragt Server-Adresse,
Token und Konto ab (mit Erreichbarkeitsprüfung) — danach ist das System
einsatzbereit. Der Assistent lässt sich jederzeit erneut aufrufen:

```bash
mailarc setup       # schreibt ~/.config/mailarc/config.env
mailarc account list
mailarc sync run
```

## Hinweise

- **PDF-Export (WeasyPrint):** Der `.pkg`-Build lässt WeasyPrint samt nativer Libs
  (pango/cairo) **bewusst weg** — es ließe sich nur schwer zuverlässig bündeln.
  `mailarc search pdf` zeigt dann eine klare Meldung statt zu crashen; alle anderen
  Funktionen sind vollständig verfügbar. Wer PDF im Paket braucht, entfernt in
  `build.sh` den `weasyprint`-Filter und das `--exclude-module weasyprint` und
  liefert die Dylibs mit.

- **Python-Version:** PyInstaller unterstützt brandneue Python-Releases manchmal
  verzögert. Falls der Build daran scheitert, ein 3.12/3.13 verwenden:
  ```bash
  PYTHON=/opt/homebrew/bin/python3.12 packaging/macos/build.sh
  ```
- **Signierung/Notarisierung:** `.pkg` und `.dmg` werden unsigniert erzeugt.
  Für die Verteilung außerhalb des eigenen Rechners sollten sie signiert
  (`productsign` / `codesign`) und notarisiert (`notarytool`) werden, sonst
  blockt Gatekeeper. Identifier: `de.microtronix.mailarc`.
- **Layout anpassen:** Farben/Texte des Hintergrunds liegen in `brand.py` bzw.
  `make_background.py`. Die Icon-Position (`ICON_POS`) muss mit dem
  `create-dmg --icon`-Aufruf in `build.sh` übereinstimmen.

## Dateien

| Datei | Zweck |
|-------|-------|
| `build.sh` | Orchestriert den gesamten Build |
| `brand.py` | Farben, Schriften, App-Icon-Zeichnung |
| `make_icon.py` | erzeugt `AppIcon.icns` |
| `make_background.py` | erzeugt DMG-Hintergrund (@1x/@2x) |
| `entry.py` | PyInstaller-Einstiegspunkt |
| `distribution.xml` | productbuild-Definition (Begrüßung/Lizenz/Abschluss) |
| `scripts/postinstall` | Symlink nach `/usr/local/bin` |
| `resources/` | Welcome-/Conclusion-HTML, Lizenztext |
