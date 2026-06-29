# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [PEP 440](https://peps.python.org/pep-0440/).

## [2.0.0.0] – 2026-06-29

Schwerpunkt dieses Releases ist die **native macOS-Auslieferung** sowie eine
präzisere Volltextsuche.

### Hinzugefügt
- **macOS-Installationspakete (`.pkg` und `.dmg`).** Neues `packaging/macos/`
  baut aus dem Quellbaum ein eigenständiges Installationspaket mit eingebettetem
  Python (PyInstaller) – auf dem Zielrechner muss nichts vorinstalliert sein.
  - One-Shot-Build über `packaging/macos/build.sh`.
  - App-Icon (`.icns`) und DMG-Hintergrund (Retina, @1x/@2x) werden vollständig
    aus Code erzeugt (`brand.py`, `make_icon.py`, `make_background.py`).
  - Installer mit Begrüßung, Lizenz und Abschlussseite (`productbuild`); legt
    `mailarc` per Symlink unter `/usr/local/bin` an.
- **Exakte Phrasensuche** für die Volltextsuche: `mailarc search query --phrase`
  (Kurzform `-x`) und `mailarc search count --phrase`. Mehrteilige Suchstrings
  wie `26/130` matchen nur noch, wenn die Tokens direkt aufeinanderfolgen, statt
  per ODER einzeln zu treffen.

### Geändert
- Versionsschema auf vierstellig umgestellt (`2.0.0.0`).

### Hinweise
- Die erzeugten `.pkg`/`.dmg` sind **unsigniert**. Für die Verteilung außerhalb
  des Build-Rechners sollten sie signiert (`productsign`/`codesign`) und
  notarisiert (`notarytool`) werden, sonst blockt Gatekeeper. Identifier:
  `de.microtronix.mailarc`.

## [1.0.0] – 2026

### Hinzugefügt
- Erste Version: read-only IMAP-Import nach SQLite, Indexierung in
  Elasticsearch, Volltextsuche, Statistiken und PDF-/Office-Anhang-Extraktion
  über die `mailarc`-CLI.

[2.0.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v2.0.0.0
[1.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v1.0.0
