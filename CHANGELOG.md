# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [PEP 440](https://peps.python.org/pep-0440/).

## [2.5.0.0] – 2026-08-04

Schwerpunkt dieses Releases ist die **Erstinstallation „ready to use"**: ein
Einrichtungs-Assistent und der macOS-Installer, der ihn anbietet.

### Hinzugefügt
- **`mailarc setup`** – schreibt interaktiv die globale Bootstrap-Konfiguration
  (`~/.config/mailarc/config.env`, 0600): Server-URL, Token (verdeckt), Konto.
  Prüft die Server-Erreichbarkeit und bietet die vorhandenen Konten zur Auswahl.
  Skriptbar über `--non-interactive` samt `--base-url/--token/--account/--verify`.
- **macOS-Installer richtet optional ein:** das `postinstall`-Skript fragt am Ende
  (per Dialog, im Kontext des angemeldeten Nutzers), ob `mailarc setup` jetzt in
  einem Terminal laufen soll — so ist ein frisches System nach dem `.pkg`/`.dmg`
  direkt einsatzbereit.

### Geändert
- **PDF-Export degradiert sauber:** WeasyPrint-Verfügbarkeit wird beim Import
  erkannt (`render.WEASYPRINT_OK`); fehlt es (z. B. im macOS-Paket, das die nativen
  Libs bewusst nicht bündelt), zeigen `search pdf`/`pdf-batch` eine klare Meldung
  statt eines Stacktrace. `build.sh` schließt WeasyPrint aus dem Bundle aus.

## [2.4.0.0] – 2026-08-04

Schwerpunkt dieses Releases ist der **PDF-Export von Mail-Inhalten**: HTML-Mails
lassen sich einzeln oder für ganze Suchergebnisse als sauber gerendertes PDF
speichern.

### Hinzugefügt
- **`mailarc search pdf <ID>`** – rendert den `text/html`-Teil einer archivierten
  Mail per **WeasyPrint** zu einem PDF (Kopfzeilen + Inhalt). Auflösung über
  `mailbox:uidvalidity:uid` oder Message-ID, analog zu `search download`.
- **Inline-Bilder** (`cid:`) werden aus der Roh-Mail als `data:`-URI eingebettet,
  sodass das PDF autark ist. Reine Text-Mails werden ebenfalls als PDF ausgegeben.
- **Datenschutz-Default:** extern verlinkte Bilder (http/https) sind blockiert und
  werden nur mit `--load-remote` geladen (verhindert Tracking-Pixel).
- Optionen `--out` (Datei oder Verzeichnis; Dateiname sonst aus dem Betreff) und
  `--open` (PDF nach dem Erstellen öffnen).
- **`mailarc search pdf-batch`** – erzeugt PDFs für **alle Treffer einer Suche**
  in einem Lauf (gleiche Filter wie `search query`). Namensschema
  `<prefix>_<datum>[_lfdnr].pdf` (`--prefix/-p`): Mail-Datum als `YYYY-MM-DD`, eine
  **lfd. Nummer nur bei Datumsgleichheit** (chronologisch, nullgepolstert).
  Einzelne Mails ohne Inhalt / mit Render-Fehler werden übersprungen, ohne den
  Batch abzubrechen.
- Neue Abhängigkeit **`weasyprint>=63`** (native Libs, macOS: `brew install pango`).

## [2.3.0.0] – 2026-08-04

Schwerpunkt dieses Releases ist die **vollständig zentrale Konfiguration**: neben
den IMAP-Zugangsdaten kann jetzt auch die restliche Konfiguration zentral je Konto
liegen — die lokale `.env` schrumpft auf einen einmaligen Bootstrap.

### Hinzugefügt
- **Globale Bootstrap-`.env`:** `mailarc` sucht die Konfiguration in aufsteigender
  Priorität unter `~/.config/mailarc/config.env` (bzw. `$XDG_CONFIG_HOME`),
  projektlokaler `./.env` und `$MAILARC_ENV`. Eine **einzige** globale Datei genügt
  damit für alle Verzeichnisse. Vorlage: `.env.bootstrap.example`.
- **Zentrale Zusatz-Config je Konto:** Elasticsearch-Ziel (Host/User/Passwort/
  Index/Verify) und Anhang-Optionen liegen optional im mailarc-server und werden
  zur Laufzeit angewandt (`ensure_central_config`, jetzt auch beim `index`/`search`
  über `es.client()`). Gesetzte Felder überschreiben die lokale `.env`, nicht
  gesetzte bleiben auf dem lokalen Default.
- **`mailarc account config <label>`** zum Setzen dieser Zentral-Config;
  `--from-env` übernimmt die aktuell geladenen lokalen Werte in einem Rutsch
  (Migration der `.env`).
- **`account list` zeigt jetzt die vollständige Config je Konto** (IMAP + ES +
  Anhang) und markiert zentral nicht gesetzte Felder. Ein hinterlegter ES-Host
  ohne ES-Passwort wird explizit als wahrscheinliche **ES-401-Ursache** angemerkt.
  `--show-secrets` gibt die Passwörter zum Debuggen im Klartext aus. Der Server
  meldet dafür in `AccountOut` neu `es_password_set` (nie das Passwort selbst).

### Serverseitig (mailarc-server)
- `account`-Tabelle um ES-Felder (inkl. **Fernet-verschlüsseltem** `es_password_enc`)
  und Anhang-Optionen erweitert; automatische Spalten-Migration beim Start
  (`ALTER TABLE ADD COLUMN` für Bestands-DBs).
- Neuer Endpoint **`GET /accounts/{name}/config`** liefert das vollständige Profil
  (IMAP + ES + Anhang) mit entschlüsselten Secrets; `POST`/`PATCH /accounts`
  akzeptieren die neuen Felder. `GET /credentials` bleibt für ältere Clients.

### Sicherheit
- Auch das ES-Passwort liegt nur noch verschlüsselt in der zentralen DB. Der
  Bootstrap (`REST_API_TOKEN`, `REST_BASE_URL`, `ACCOUNT`) muss lokal bleiben —
  er ist der Schlüssel zum zentralen Speicher (Henne-Ei) und lässt sich nicht
  selbst dort ablegen.
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

[2.5.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v2.5.0.0
[2.4.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v2.4.0.0
[2.3.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v2.3.0.0
[2.1.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v2.1.0.0
[2.0.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v2.0.0.0
[1.0.0]: https://github.com/saggi1967/imap-archiver/releases/tag/v1.0.0
