<div align="center">

# 📬 imap-archiver

**Read-only IMAP-Mailarchiv mit Volltextsuche – von der Mailbox in SQLite und Elasticsearch.**

[![Version](https://img.shields.io/badge/version-2.1.0.0-blue)](#)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](#)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.x-005571?logo=elasticsearch&logoColor=white)](#)
[![CLI](https://img.shields.io/badge/CLI-Typer%20%2B%20Rich-009688)](#)
[![License](https://img.shields.io/badge/license-proprietär-lightgrey)](#lizenz)

</div>

---

`imap-archiver` ist ein CLI-Werkzeug, das E-Mails **rein lesend** von einem IMAP-Server
herunterlädt, sie **unverändert** (Roh-RFC822 + geparste Felder) in einer lokalen
SQLite-Datenbank ablegt und für die Suche **suchoptimal nach Elasticsearch**
indexiert – inklusive **Volltext aus PDF-, DOCX- und XLSX-Anhängen**. Auf dem
Mailserver wird dabei **nichts gelöscht oder verändert**.

```
┌────────────┐   read-only    ┌────────────┐    extract     ┌───────────────┐
│ IMAP-Server│ ─────────────▶ │  SQLite    │ ─────────────▶ │ Elasticsearch │
│ (EXAMINE)  │   UID-Sync     │ Roh-RFC822 │  Body+Anhänge  │  Volltext-Idx │
└────────────┘                └────────────┘                └───────────────┘
      mailarc sync               mailarc stats                 mailarc search
```

## Inhalt

- [Funktionsumfang](#funktionsumfang)
- [Architektur & Pipeline](#architektur--pipeline)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Verwendung](#verwendung)
  - [1 · Import (IMAP → SQLite)](#1--import-imap--sqlite)
  - [2 · Statistik](#2--statistik)
  - [3 · Indexierung (SQLite → Elasticsearch)](#3--indexierung-sqlite--elasticsearch)
  - [4 · Suche & Anhang-Download](#4--suche--anhang-download)
- [Befehlsübersicht](#befehlsübersicht)
- [Datenmodell](#datenmodell)
- [Sicherheit](#sicherheit)
- [Projektstruktur](#projektstruktur)
- [Lizenz](#lizenz)

## Funktionsumfang

| | Funktion |
|---|---|
| 🔒 | **Read-only Import** – Ordner werden mit `EXAMINE` geöffnet; keine Schreib-/Löschbefehle |
| 🔁 | **Inkrementeller Sync** – pro Ordner `UIDVALIDITY` + höchste `UID`; nur Neues seit letztem Lauf |
| 🗄️ | **Unveränderte Ablage** – komplettes RFC822-Rohbyte + geparste Kopffelder in SQLite |
| 🔎 | **Suchoptimale Indexierung** – `german`-Analyzer, exakte Adress-Filter, Zeitraum, Anhang-Flag |
| 📎 | **Anhang-Volltext** – Text aus PDF / DOCX / XLSX / Textdateien wird durchsuchbar |
| 📊 | **Statistiken** – Mails pro Jahr/Monat/Wochentag, Top-Absender, Größen – farbig im Terminal |
| 📥 | **Quickview & Download** – neueste Mails im Mail-Client-Stil, Anhänge als Dateien speichern |
| 🎨 | **Schöne CLI** – Typer + Rich: Fortschrittsbalken, Tabellen, Highlights, Start-Banner |

## Architektur & Pipeline

Vier Stufen, die unabhängig voneinander laufen und über die SQLite-DB gekoppelt sind:

1. **Import** (`sync`) – IMAP → SQLite, read-only, UID-basiert inkrementell.
2. **Statistik** (`stats`) – Auswertung direkt auf der lokalen DB, ohne Server.
3. **Indexierung** (`index`) – SQLite → Elasticsearch; extrahiert Body & Anhang-Text.
4. **Suche** (`search`) – komfortable Abfragen über den E-Mail-Index, Anhang-Download aus der DB.

## Installation

> Voraussetzungen: **Python ≥ 3.12** und ein erreichbarer IMAP- bzw. Elasticsearch-Server (9.x).

```bash
git clone git@github.com:saggi1967/imap-archiver.git
cd imap-archiver

python -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env        # Zugangsdaten eintragen (siehe unten)
```

Danach steht der Befehl **`mailarc`** zur Verfügung (solange die venv aktiv ist).

### Elasticsearch & Kibana per Docker

Wer keinen eigenen Elasticsearch-Server betreibt, startet den kompletten
Suchstack lokal mit der mitgelieferten [`docker-compose.yml`](docker-compose.yml):

```bash
# In der .env ein Passwort setzen (sonst Fallback "changeme"):
#   ES_PASSWORD=deinPasswort
#   KIBANA_PASSWORD=einAnderesPasswort   # optional

docker compose up -d
docker compose logs -f kibana       # warten bis Status "available"
```

Danach erreichbar:

| Dienst | URL | Login |
|---|---|---|
| Elasticsearch | <http://localhost:9200> | `elastic` / `ES_PASSWORD` |
| Kibana | <http://localhost:5601> | `elastic` / `ES_PASSWORD` |

Der Stack läuft als **Single-Node** mit aktivierter Security (Basic-Auth), aber
ohne TLS auf der HTTP-Schicht – passend zum Default `ES_HOST=http://localhost:9200`.
Daten liegen im Docker-Volume `es-data` und bleiben über Neustarts erhalten.
In Kibana lässt sich unter **Discover** eine Data View auf den Index `emails`
anlegen, um die archivierten Mails durchzusehen.

```bash
docker compose down        # stoppen (Daten bleiben erhalten)
docker compose down -v     # stoppen + Index-Daten löschen
```

## Konfiguration

Alle Einstellungen kommen aus Umgebungsvariablen bzw. einer `.env`-Datei
(via `pydantic-settings`). Vorlage: [`.env.example`](.env.example).

| Variable | Default | Bedeutung |
|---|---|---|
| `IMAP_HOST` | `localhost` | Hostname des IMAP-Servers |
| `IMAP_PORT` | `993` | Port (993 = IMAPS) |
| `IMAP_SSL` | `true` | TLS verwenden |
| `IMAP_SSL_VERIFY` | `true` | Zertifikat prüfen – bei Hostname-Mismatch bewusst `false` |
| `IMAP_USER` / `IMAP_PASSWORD` | – | Zugangsdaten |
| `IMAP_FOLDERS` | `INBOX` | Komma-getrennte Ordnerliste |
| `DB_PATH` | `mailarc.db` | Pfad zur SQLite-Datei |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch-Basis-URL |
| `ES_USER` / `ES_PASSWORD` | `elastic` / – | Basic-Auth |
| `ES_INDEX` | `emails` | Ziel-Index |
| `ES_VERIFY_CERTS` | `true` | Zertifikatsprüfung (nur bei `https`) |
| `ATTACHMENT_TEXT` | `true` | Anhang-Volltext extrahieren |
| `ATTACHMENT_MAX_BYTES` | `25000000` | größere Anhänge überspringen |
| `ATTACHMENT_MAX_CHARS` | `100000` | extrahierten Text je Mail begrenzen |

> 🔐 Passwörter gehören **ausschließlich** in die `.env` (per `.gitignore` vom Commit ausgeschlossen).

## Verwendung

Typischer End-to-End-Ablauf:

```bash
mailarc db init                 # 1. SQLite-Schema anlegen
mailarc status folders          #    verfügbare IMAP-Ordner ansehen
mailarc sync run                # 2. Mails importieren (read-only)
mailarc stats show              #    Statistiken ansehen
mailarc index run               # 3. nach Elasticsearch indexieren
mailarc search recent           # 4. neueste Mails / suchen / herunterladen
```

### 1 · Import (IMAP → SQLite)

```bash
mailarc sync run                      # alle Ordner aus IMAP_FOLDERS
mailarc sync run -f INBOX -f Sent     # bestimmte Ordner
mailarc sync run --full               # Voll-Import erzwingen
mailarc status show                   # Sync-Stand & Mail-Anzahl je Ordner
```

Beim **ersten Lauf** werden alle Mails geladen, bei **Folgeläufen** nur die seit
dem letzten Import neuen (`UID > last_uid`). Ändert der Server die `UIDVALIDITY`,
erfolgt automatisch ein Voll-Resync des betroffenen Ordners.

### 2 · Statistik

```bash
mailarc stats show          # Jahre, Monate, Wochentage, Top-Absender, Größen
mailarc stats show -n 20    # Top 20 Absender
```

### 3 · Indexierung (SQLite → Elasticsearch)

```bash
mailarc index init          # Index + Mapping anlegen (idempotent)
mailarc index run           # nur noch nicht indexierte Mails senden
mailarc index run --reindex # alle Mails neu senden (z. B. nach Mapping-Änderung)
```

Jede Mail wird zu einem suchoptimalen Dokument: `german`-Analyzer für Betreff/Body,
lowercase-`keyword` für Adressen/Domain, echtes `date`-Feld, `nested` Anhänge und
das durchsuchbare Feld `attachment_text` (PDF/DOCX/XLSX/Text). Die Dokument-ID
`mailbox:uidvalidity:uid` macht das Senden **idempotent**; ein `es_indexed_at`-Stempel
sorgt für **inkrementelles** Indexieren. Es ist **kein** ES-Plugin (Tika/ingest) nötig.

### 4 · Suche & Anhang-Download

```bash
mailarc search recent                          # Quickview: neueste Mails (Mail-Client-Stil)
mailarc search recent -n 100 --last 7d         # mehr Treffer, nur letzte 7 Tage
mailarc search query "Angebot Gebühren"        # Volltext (Betreff/Body/Absender/Anhang)
mailarc search query rechnung --domain firma.de --last 30d
mailarc search query -s Protokoll --attachments
mailarc search query --file .pdf --since 2026-01-01
mailarc search show INBOX:7:42                  # eine Mail vollständig anzeigen
mailarc search download INBOX:7:42 -o ~/Downloads   # Anhänge als Dateien speichern
mailarc search top --by from_domain             # häufigste Absender-Domains
```

Trefferlisten zeigen eine **ID-Spalte** (`mailbox:uidvalidity:uid`), die direkt für
`search show` und `search download` verwendbar ist (alternativ die Message-ID).
`download` liest die Originalbytes aus der lokalen DB, entschärft Dateinamen
(kein Pfad-Ausbruch) und vermeidet Überschreiben durch `name (1).ext`.

## Befehlsübersicht

| Befehl | Zweck |
|---|---|
| `mailarc db init` | SQLite-Schema anlegen / migrieren |
| `mailarc sync run` | Mails read-only importieren (Voll/inkrementell) |
| `mailarc status show` / `folders` | Sync-Stand bzw. IMAP-Ordner anzeigen |
| `mailarc stats show` | Farbige Statistiken über die geladenen Mails |
| `mailarc index init` / `run` | Index/Mapping anlegen, Mails indexieren |
| `mailarc search query` | Volltextsuche mit Filtern, Zeitraum, Highlight |
| `mailarc search recent` | Neueste Mails als Quickview |
| `mailarc search show` | Einzelne Mail vollständig (Header, Anhänge, Body) |
| `mailarc search download` | Anhänge einer Mail als Dateien speichern |
| `mailarc search count` / `top` | Treffer zählen / Häufigkeits-Aggregation |
| `mailarc --version` | Version & Banner |

Jeder Befehl bringt mit `--help` konkrete Beispiele mit.

## Datenmodell

**SQLite** (`DB_PATH`):

- `mailbox(name, uidvalidity, last_uid, last_import_at)` – Sync-Stand je Ordner
- `email(mailbox_id, uid, uidvalidity, message_id, from_addr, to_addr, subject,
  date_header, internaldate, size, raw, imported_at, es_indexed_at)` – Roh-Mail + Felder

Eindeutigkeit über `(mailbox_id, uidvalidity, uid)` verhindert Doppel-Importe.

**Elasticsearch** (`ES_INDEX`): u. a. `subject`, `body`, `attachment_text` (Volltext,
`german`), `from_addr`/`from_domain`/`to`/`cc` (keyword, lowercase), `date`,
`has_attachment`, `attachment_count`, `attachments` (nested: filename/typ/size/has_text).

## Sicherheit

- **Read-only IMAP**: Ordner werden mit `EXAMINE` geöffnet – es werden ausschließlich
  lesende Befehle abgesetzt. Es kann serverseitig nichts gelöscht oder verändert werden.
- **Keine Secrets im Repo**: Zugangsdaten nur in `.env` (gitignored).
- **Sichere Downloads**: Anhang-Dateinamen werden von Pfadanteilen befreit; Kollisionen
  überschreiben nichts.

## Projektstruktur

```
imap_archiver/
├── app/
│   ├── config.py        # Einstellungen (.env)
│   ├── db.py            # SQLite-Schema, Migrationen, Zugriff
│   ├── imap.py         # read-only IMAP (EXAMINE, UID-Suche)
│   ├── sync.py         # Import-Logik (initial/inkrementell/resync)
│   ├── extract.py      # RFC822 → suchoptimales Dokument
│   ├── attachments.py  # Text aus PDF/DOCX/XLSX/Text
│   ├── es.py           # ES-Client + Mapping
│   ├── main.py         # CLI-Einstieg, Banner, --version
│   └── commands/       # db, sync, status, stats, index, search
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## Zentrale Speicherung (optional)

Standardmäßig legt jede CLI-Instanz ihre Mails lokal in einer eigenen
SQLite-Datei ab. Alternativ können **mehrere Instanzen in eine gemeinsame
zentrale Datenbank** sammeln — hinter dem separaten REST-Service
[`mailarc-server`](../mailarc-server) (FastAPI + Postgres).

Das Backend ist umschaltbar, ohne dass sich an der Bedienung etwas ändert:

```bash
# in der .env:
STORAGE_BACKEND=rest
REST_BASE_URL=https://archiv.firma.example
REST_API_TOKEN=dein-token
```

Alle Befehle (`sync`, `index`, `status`, `stats`, `search download`) arbeiten
dann gegen den zentralen Service statt gegen die lokale SQLite-Datei. Der Sync
lädt die Mails in **200er-Batches** als asynchrone Jobs hoch und pollt den
Fortschritt; die Idempotenz `(Ordner, UIDVALIDITY, UID)` verhindert Duplikate,
sodass mehrere Instanzen denselben Ordner gefahrlos parallel abholen können.

### Zentrale IMAP-Zugangsdaten (statt Passwort je `.env`)

Bei `STORAGE_BACKEND=rest` müssen die IMAP-Zugangsdaten nicht mehr in jeder
Client-`.env` stehen. Der Zugang wird einmal **interaktiv** angelegt und liegt
danach **verschlüsselt** im zentralen Service:

```bash
mailarc account add        # fragt Host, Benutzer, Passwort (verdeckt), Ordner ab
mailarc account list       # zeigt alle Konten (ohne Passwort)
mailarc account remove <label>
```

In der `.env` dieses Clients genügt dann das Konto-Label — Host, Benutzer,
Passwort und Ordnerliste kommen zur Laufzeit vom Server, die `IMAP_*`-Felder
werden ignoriert:

```bash
STORAGE_BACKEND=rest
REST_BASE_URL=https://archiv.firma.example
REST_API_TOKEN=dein-token
ACCOUNT=firma-stephan
```

Damit steht **kein IMAP-Passwort mehr lokal auf der Platte**. Der Client verbindet
sich weiterhin selbst read-only zum IMAP; er holt die Zugangsdaten dafür nur kurz
über HTTPS vom Service. Der Service braucht dazu einen `SECRET_KEY` (Fernet) —
Details im [`mailarc-server`](../mailarc-server)-README.

Details zu Vertrag, Nebenläufigkeit und Betrieb: siehe
[`VORSCHLAG-zentrale-speicherung.md`](VORSCHLAG-zentrale-speicherung.md) und das
[`mailarc-server`](../mailarc-server)-README.

## Lizenz

Proprietär / intern – © Microtronix. Keine Weitergabe ohne Freigabe.

---

<div align="center">
<sub>Gebaut mit Python · Typer · Rich · IMAPClient · Elasticsearch</sub>
</div>
