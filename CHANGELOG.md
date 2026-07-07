# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [PEP 440](https://peps.python.org/pep-0440/).

## [2.1.0.0] – 2026-07-07

Schwerpunkt dieses Releases sind **zentrale, verschlüsselte IMAP-Zugangsdaten** —
damit nicht mehr jede Client-Installation ihr IMAP-Passwort in der eigenen `.env`
vorhalten muss.

### Hinzugefügt
- **`mailarc account`-Befehle** (`add`, `list`, `remove`). `account add` fragt die
  Zugangsdaten interaktiv ab (Passwort verdeckt) und legt sie zentral im
  mailarc-server ab, wo das Passwort **Fernet-verschlüsselt** gespeichert wird.
- **Konto-Auswahl per `ACCOUNT`** in der `.env`: Ist bei `STORAGE_BACKEND=rest`
  ein Konto-Label gesetzt, holt der Client Host, Benutzer, Passwort und
  Ordnerliste zur Laufzeit vom Server; die lokalen `IMAP_*`-Felder werden dann
  ignoriert. So steht **kein IMAP-Passwort mehr lokal auf der Platte**.

### Serverseitig (mailarc-server 2.1.0.0)
- Neue `account`-Tabelle samt `crypto`-Modul (Fernet) und `/accounts`-Endpunkten
  (Anlegen/Auflisten/Löschen + Token-geschütztes `…/credentials`). Benötigt einen
  `SECRET_KEY` in der Server-`.env`. Die Tabelle wird beim Start automatisch
  angelegt (`create_all`). Docker-Image zieht `cryptography`, Compose reicht
  `SECRET_KEY` durch.

### Sicherheit
- Verschlüsselung schützt DB-Backups/Dumps (Encryption at Rest), **nicht** einen
  kompromittierten Server (er hält den Schlüssel). REST-Strecke über HTTPS
  betreiben; `SECRET_KEY` getrennt sichern — geht er verloren, sind gespeicherte
  Passwörter nicht mehr entschlüsselbar.

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
