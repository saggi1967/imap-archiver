# Vorschlag: Zentrale Speicherung über CRUD-REST-Service statt lokaler SQLite

> Status: **Konzept / Diskussionsgrundlage** – noch nichts implementiert.

## 1 · Ausgangslage (Ist-Zustand)

Die gesamte Persistenz läuft heute über **`app/db.py`** (SQLite). Es gibt zwei Tabellen:

| Tabelle | Zweck |
|---|---|
| `mailbox` | Sync-Stand je Ordner (`uidvalidity`, `last_uid`, `last_import_at`) |
| `email`  | Roh-RFC822 (`raw` BLOB) + geparste Felder + `es_indexed_at`-Wasserzeichen |

**Zugriffspunkte auf die DB** (das ist der Umbau-Umfang):

| Datei | Operationen |
|---|---|
| `app/sync.py` | `upsert_mailbox`, `get_mailbox`, `insert_email`, `update_mailbox_state`, `reset_mailbox_state` |
| `commands/index.py` | `iter_emails_for_index`, `count_pending_index`, `mark_indexed` |
| `commands/search.py` | `get_raw_by_ref`, `get_raw_by_message_id` (Anhang-Download) |
| `commands/stats.py` | **direktes SQL** `SELECT … FROM email` |
| `commands/status.py` | **direktes SQL** `SELECT … FROM mailbox JOIN email` |

~90 % aller Zugriffe gehen bereits sauber durch Funktionen in `db.py`. Nur `stats.py`
und `status.py` greifen mit rohem `conn.execute(...)` an der Abstraktion vorbei — die
müssen zuerst gehoben werden.

## 2 · Zielbild

```
┌────────────┐   ┌──────────────────┐   HTTP/REST   ┌────────────────┐
│ IMAP-Server│──▶│ imap-archiver CLI│──────────────▶│ CRUD-RESTService│
│ (EXAMINE)  │   │ (StorageBackend) │◀──────────────│  + zentrale DB │
└────────────┘   └──────────────────┘               └────────────────┘
                          │  (Backend austauschbar: sqlite | rest)
                          ▼
                   Elasticsearch (bleibt)
```

Mehrere CLI-Instanzen sammeln ihre Mails in **einer** zentralen Datenbank hinter einem
REST-Service, statt jeweils lokal.

## 3 · Kern-Idee: Storage-Backend-Abstraktion

Ein **Protokoll** `StorageBackend` mit genau den o. g. Operationen; zwei Implementierungen:

- `SqliteStorage` – kapselt den heutigen Code (bleibt Default, volle Abwärtskompatibilität)
- `RestStorage` – spricht den REST-Service über `httpx`

Umschaltbar per Konfiguration:

```env
STORAGE_BACKEND=sqlite        # oder: rest
REST_BASE_URL=https://archiv.microtronix.de/api
REST_API_TOKEN=…              # Bearer-Auth
REST_VERIFY_CERTS=true
```

## 4 · Vorgeschlagener REST-Vertrag (CRUD)

| Methode & Pfad | Ersetzt | Anmerkung |
|---|---|---|
| `GET /mailboxes/{name}` | `get_mailbox` | |
| `POST /mailboxes` | `upsert_mailbox` | idempotent (Name unique) |
| `PATCH /mailboxes/{id}` | `update_/reset_mailbox_state` | Sync-Stand, Wasserzeichen **nur vorwärts** |
| `GET /mailboxes?with_counts=1` | `status.py` | Server aggregiert Zählung |
| `POST /emails` | `insert_email` | **idempotent** über `(mailbox,uidvalidity,uid)`; `201`=neu / `200`=schon da |
| `POST /sync-jobs` | Sync-Batch | **asynchron**, siehe Abschnitt 6 |
| `GET /emails?index_pending=1&cursor=…` | `iter_emails_for_index` | **paginiert/streaming** |
| `GET /emails/count?reindex=…` | `count_pending_index` | |
| `PATCH /emails/mark-indexed` | `mark_indexed` | Bulk-Liste von IDs |
| `GET /emails/{mb}/{uidv}/{uid}/raw` | `get_raw_by_ref` | liefert `raw`-Bytes |
| `GET /emails/by-message-id/{mid}/raw` | `get_raw_by_message_id` | |
| `GET /stats/summary` | `stats.py` | **Aggregation serverseitig** statt alle Zeilen laden |

## 5 · Nebenläufigkeit (zwei CLIs syncen gleichzeitig)

**Konflikt-Einheit ist der Ordner, nicht der Service.** Zwei CLIs, die *verschiedene*
Ordner syncen, stören sich nicht und dürfen parallel laufen. Eine *globale* Sperre
(„es läuft schon ein Sync") wäre zu grob und würde unabhängige Ordner unnötig serialisieren.

Kritisch ist nur: zwei CLIs auf **denselben** Ordner.

### 5.1 · Korrektheit kommt aus Idempotenz, nicht aus Sperren

Paralleler Sync desselben Ordners ist **datensicher**, wenn zwei Dinge gelten:

1. **Insert idempotent** — wie heute `INSERT OR IGNORE` über `(mailbox, uidvalidity, uid)`.
   Laden beide dieselbe Mail, gewinnt eine, die andere bekommt „schon vorhanden".
   Kein Duplikat, keine Korruption.
2. **Wasserzeichen nur vorwärts** — `last_uid` per `MAX(last_uid, :neu)` statt blind
   überschreiben. Dann ist egal, wer zuletzt schreibt.

Schlimmster Fall bei Parallellauf: *doppelte IMAP-Arbeit* (beide holen dieselben Mails),
**nicht** Datenmüll.

> Heutiger SQLite-Zustand zum Vergleich: zwei CLIs auf dieselbe `mailarc.db` → SQLite
> sperrt die **ganze** Datei, die zweite bekommt `database is locked`. Also faktisch
> harte globale Sperre — unfreiwillig und grob. Der REST-Umbau macht das besser.

### 5.2 · Advisory-Lock pro Ordner (Effizienz-Schicht)

Zusätzlich zur Idempotenz ein **Lock pro Ordner**, damit die zweite CLI die doppelte
IMAP-Arbeit gar nicht erst macht:

```
POST /mailboxes/INBOX/sync-lock   → 200 {lease_id, expires_at}   (Lock bekommen)
                                  → 409 Conflict {locked_until}   (läuft schon → Ordner skippen)
DELETE /mailboxes/INBOX/sync-lock → Lock freigeben (im finally!)
```

Die zweite CLI überspringt bei `409` **genau diesen Ordner**, macht aber andere weiter.

### 5.3 · Wichtigster Fallstrick: Stale Locks

Stürzt eine CLI mitten im Sync ab und der Lock hat kein Ablaufdatum, ist der Ordner
für immer gesperrt. Deshalb:

- Lock als **Lease mit TTL** (z. B. 5 Min); bei langen Läufen **Heartbeat** zum Verlängern.
- Läuft die Lease ab → Server gibt den Ordner automatisch frei.

**Merksatz:** Locking = Effizienz, Idempotenz = Korrektheit. Die Idempotenz macht dich
unabhängig davon, dass das Locking perfekt funktioniert.

## 6 · Timeouts & asynchrone Verarbeitung (Job + Polling)

**Problem:** Ein Sync-Batch mit vielen/großen Mails (Anhänge bis 25 MB) kann serverseitig
länger dauern als ein HTTP-Timeout erlaubt. Ein synchroner `POST` würde ins Timeout laufen,
obwohl der Server noch fleißig arbeitet — und der Client weiß nicht, ob's geklappt hat.

### 6.0 · Der Kern: zwei verschiedene Timeouts, zwei verschiedene Hebel

Die naheliegende Frage — *„alles auf einmal async übergeben und lokal pollen"* **vs.** *„kleine
Pakete schicken und ggf. im Timeout landen"* — ist ein **Scheingegensatz**. Es sind zwei
unterschiedliche Zeitfresser, jeder mit seinem eigenen Hebel:

| Zeitfresser | Wogegen | Hebel |
|---|---|---|
| **Upload** (Bytes über die Leitung) | großer Request = großes Upload-Timeout-Risiko + RAM-Explosion | **kleine, idempotente Batches** (~200 Mails, gzip) |
| **Verarbeitung** (validieren, dedupen, in zentrale DB schreiben) | dauert evtl. länger als jedes HTTP-Timeout | **async Job + Poll** (läuft außerhalb des Requests → gar kein HTTP-Timeout mehr) |

Ein synchroner `POST` mit *allem* presst **beide** in denselben Request — genau das läuft ins
Timeout. Die Lösung ist deshalb **nicht** das eine *oder* das andere, sondern **beides
zusammen**: kleine Batches lösen das Upload-Timeout, async+Poll löst das Verarbeitungs-Timeout.
Ein einzelner Riesen-Upload „async" ist der schlechteste Fall — er behält das Upload-/RAM-Risiko
und gewinnt nur beim Verarbeitungsteil.

**Lösung (deine Idee, verfeinert): Upload entkoppeln von Verarbeitung.** Der HTTP-Request
muss nur den **Upload** überleben, nicht die Verarbeitung. Ablauf:

```
1. POST /sync-jobs        Client lädt Batch hoch
   → 202 Accepted {tx_id, status:"accepted"}     Server nimmt an, verarbeitet asynchron
2. (Server arbeitet intern: validieren, dedupen, in zentrale DB schreiben)
3. GET /sync-jobs/{tx_id} Client pollt zyklisch
   → {status, processed, total, errors[]}         status: pending|running|done|failed
4. Client pollt mit Backoff bis status ∈ {done, failed}
```

### 6.1 · Wichtige Verfeinerung: nicht rein RAM, sondern durables Staging

Deine Formulierung war „im lokalen Speicher (memory) parken". Reines RAM ist riskant:

- **Crash = Datenverlust** — der Client denkt, er hätte hochgeladen, aber der Server
  hat die geparkten Mails nach einem Neustart verloren.
- **RAM-Explosion** — bei großen Batches (25-MB-Anhänge × viele Mails) läuft der
  Server-Speicher voll.

**Empfehlung:** Upload in einen **durablen Staging-Bereich** schreiben (Staging-Tabelle,
Queue oder Objektspeicher), *dann* `202` zurückgeben, *dann* async in den Hauptbestand
verarbeiten. Gleiche Poll-Semantik, aber crash-fest.

### 6.2 · Timeout-Strategie im Detail

- **Zwei getrennte Timeouts:** kurzer Upload-Timeout je Batch; die Verarbeitung hat gar
  keinen HTTP-Timeout mehr (läuft ja außerhalb des Requests). Genau das ist der Gewinn.
- **Batching statt Riesen-Request:** Sync in 200er-Blöcken hochladen (wie heute `BATCH=200`),
  optional gzip. Kleinere Requests = kleineres Timeout-Risiko.
- **Idempotenter Retry:** jeder Batch trägt einen **Idempotency-Key**. Läuft ein Upload
  ins Timeout und wird wiederholt, erkennt der Server den Key und dupliziert nicht.
  (Deckt sich mit der `(mailbox,uidvalidity,uid)`-Idempotenz aus Abschnitt 5.)
- **Poll mit Backoff:** z. B. Start 1 s, bis max. 10 s; Abbruch nach globalem Deadline.

### 6.3 · Passt zur bestehenden CLI

Die CLI hat über Rich bereits Fortschrittsbalken (`commands/index.py`, `sync.py` mit
`on_tick`). Die Poll-Antwort `{processed, total}` lässt sich **direkt** auf den vorhandenen
Balken mappen — der Nutzer sieht denselben Live-Fortschritt wie heute, nur gespeist aus
dem Server-Job statt aus der lokalen Schleife.

### 6.4 · Wann synchron, wann asynchron?

- **Asynchron (Job + Poll):** Sync-Import (viele Schreibvorgänge), evtl. Reindex-Anstoß.
- **Synchron (einfacher `GET`):** Lesen wie `search download`, `status`, `stats/summary` —
  klein und schnell, kein Job-Overhead nötig.

## 7 · Weitere Entscheidungspunkte / Risiken

1. **Roh-Bytes über HTTP** — `index run` liest heute *alle* `raw` aus der DB. Über REST
   zöge das jede Mail komplett übers Netz. Empfehlung: Index-Lauf serverseitig ausführen
   oder Extraktion nahe an die zentrale DB verlagern.
2. **Auth & Transport** — Bearer-Token/mTLS, TLS erzwingen, Timeouts + Backoff-Retry.
3. **Offline-Betrieb** — heute läuft alles ohne Netz. Optional SQLite als lokaler
   Cache/Fallback (Hybrid), sonst ist die CLI ohne Service arbeitsunfähig.
4. **Der Service selbst existiert noch nicht** — separater Service, Vorschlag
   **FastAPI + SQLAlchemy** (Postgres als zentrale DB), passt zum `pydantic-settings`-Stack.

## 8 · Umsetzung in Phasen

1. **Refactor (ohne Verhaltensänderung):** `stats.py` & `status.py` von rohem SQL auf
   `db.py`-Funktionen heben → alle Zugriffe laufen durch eine Schnittstelle.
2. **Abstraktion einziehen:** `StorageBackend`-Protokoll + `SqliteStorage`, Aufrufer auf
   `storage.…` umstellen. Verhalten identisch, Default bleibt SQLite.
3. **REST-Service bauen** (separates Repo): FastAPI, zentrale DB, CRUD + Sync-Jobs + Locks.
4. **`RestStorage` implementieren** + Config-Schalter, mit Batching/Retry/gzip.
5. **Index-Strategie klären** (7.1) — voraussichtlich größter Einzelposten.
6. **Migrationsskript** bestehende `mailarc.db` → zentraler Service.
