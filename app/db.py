"""SQLite-Zugriff und Schema für die Roh-Mail-Ablage."""

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS mailbox (
    id             INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL UNIQUE,
    uidvalidity    INTEGER,
    last_uid       INTEGER NOT NULL DEFAULT 0,
    last_import_at TEXT
);

CREATE TABLE IF NOT EXISTS email (
    id           INTEGER PRIMARY KEY,
    mailbox_id   INTEGER NOT NULL REFERENCES mailbox(id),
    uid          INTEGER NOT NULL,
    uidvalidity  INTEGER NOT NULL,
    message_id   TEXT,
    from_addr    TEXT,
    to_addr      TEXT,
    subject      TEXT,
    date_header  TEXT,
    internaldate TEXT,
    size         INTEGER,
    raw          BLOB    NOT NULL,
    imported_at  TEXT    NOT NULL,
    es_indexed_at TEXT,
    UNIQUE (mailbox_id, uidvalidity, uid)
);

CREATE INDEX IF NOT EXISTS idx_email_message_id ON email (message_id);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Migration für DBs, die vor Stufe 3 angelegt wurden: erst Spalte ergänzen,
    # dann den darauf basierenden Index anlegen (sonst „no such column").
    _ensure_column(conn, "email", "es_indexed_at", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_es_pending ON email (es_indexed_at)")


def get_mailbox(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM mailbox WHERE name = ?", (name,)).fetchone()


def upsert_mailbox(conn: sqlite3.Connection, name: str) -> int:
    """Stellt sicher, dass der Ordner existiert, und gibt seine id zurück."""
    conn.execute("INSERT OR IGNORE INTO mailbox (name) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM mailbox WHERE name = ?", (name,)).fetchone()
    return row["id"]


def reset_mailbox_state(conn: sqlite3.Connection, mailbox_id: int, uidvalidity: int) -> None:
    """UIDVALIDITY hat sich geändert: alte UIDs sind ungültig, Stand zurücksetzen."""
    conn.execute(
        "UPDATE mailbox SET uidvalidity = ?, last_uid = 0 WHERE id = ?",
        (uidvalidity, mailbox_id),
    )


def update_mailbox_state(
    conn: sqlite3.Connection, mailbox_id: int, uidvalidity: int, last_uid: int, imported_at: str
) -> None:
    conn.execute(
        "UPDATE mailbox SET uidvalidity = ?, last_uid = ?, last_import_at = ? WHERE id = ?",
        (uidvalidity, last_uid, imported_at, mailbox_id),
    )


def count_pending_index(conn: sqlite3.Connection, reindex: bool) -> int:
    where = "" if reindex else "WHERE es_indexed_at IS NULL"
    return conn.execute(f"SELECT COUNT(*) FROM email {where}").fetchone()[0]


def iter_emails_for_index(conn: sqlite3.Connection, reindex: bool) -> Iterator[sqlite3.Row]:
    """Liefert Mails inkl. Ordnername und Roh-Bytes für die Indexierung."""
    where = "" if reindex else "WHERE e.es_indexed_at IS NULL"
    cur = conn.execute(
        f"""
        SELECT e.id, e.uid, e.uidvalidity, e.internaldate, e.size, e.raw,
               m.name AS mailbox
        FROM email e JOIN mailbox m ON m.id = e.mailbox_id
        {where}
        ORDER BY e.id
        """
    )
    yield from cur


def get_raw_by_ref(
    conn: sqlite3.Connection, mailbox: str, uidvalidity: int, uid: int
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT e.raw, e.subject
        FROM email e JOIN mailbox m ON m.id = e.mailbox_id
        WHERE m.name = ? AND e.uidvalidity = ? AND e.uid = ?
        """,
        (mailbox, uidvalidity, uid),
    ).fetchone()


def get_raw_by_message_id(conn: sqlite3.Connection, message_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT raw, subject FROM email WHERE message_id = ?", (message_id,)
    ).fetchone()


def mark_indexed(conn: sqlite3.Connection, email_ids: list[int], indexed_at: str) -> None:
    conn.executemany(
        "UPDATE email SET es_indexed_at = ? WHERE id = ?",
        [(indexed_at, eid) for eid in email_ids],
    )


def insert_email(conn: sqlite3.Connection, **fields) -> bool:
    """Fügt eine Mail ein. Gibt False zurück, falls sie (UID) schon vorhanden war."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO email
            (mailbox_id, uid, uidvalidity, message_id, from_addr, to_addr,
             subject, date_header, internaldate, size, raw, imported_at)
        VALUES
            (:mailbox_id, :uid, :uidvalidity, :message_id, :from_addr, :to_addr,
             :subject, :date_header, :internaldate, :size, :raw, :imported_at)
        """,
        fields,
    )
    return cur.rowcount > 0
