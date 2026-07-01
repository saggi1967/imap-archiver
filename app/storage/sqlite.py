"""SQLite-Implementierung des StorageBackend — kapselt den bisherigen ``db.py``-Code.

Verhalten ist identisch zum bisherigen ``with db.connect(...) as conn`` + Direktaufruf
der ``db.*``-Funktionen; nur die Connection ist jetzt hinter der Schnittstelle versteckt.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

from app import db
from app.storage.base import Row


class SqliteStorage:
    """StorageBackend über eine lokale SQLite-Datei (Default, volle Abwärtskompatibilität).

    Als Kontextmanager benutzen: öffnet Verbindung + Schema beim Eintritt, committet
    beim regulären Austritt und schließt immer. Bei einer Exception wird nicht
    committet (Rollback), wie beim bisherigen ``db.connect``.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._cm: object = None
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> "SqliteStorage":
        # Wiederverwendung des vorhandenen db.connect-Kontextmanagers → eine einzige
        # Stelle für row_factory, PRAGMA foreign_keys und Commit-/Close-Semantik.
        self._cm = db.connect(self._db_path)
        self._conn = self._cm.__enter__()
        db.init_schema(self._conn)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None:
        cm, self._cm, self._conn = self._cm, None, None
        return cm.__exit__(exc_type, exc, tb)

    @property
    def _c(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteStorage außerhalb des with-Blocks benutzt.")
        return self._conn

    def commit(self) -> None:
        self._c.commit()

    # -- Ordner -----------------------------------------------------------
    def get_mailbox(self, name: str) -> Row | None:
        return db.get_mailbox(self._c, name)

    def upsert_mailbox(self, name: str) -> int:
        return db.upsert_mailbox(self._c, name)

    def reset_mailbox_state(self, mailbox_id: int, uidvalidity: int) -> None:
        db.reset_mailbox_state(self._c, mailbox_id, uidvalidity)

    def reset_mailbox_full(self, mailbox_id: int) -> None:
        db.reset_mailbox_full(self._c, mailbox_id)

    def update_mailbox_state(
        self, mailbox_id: int, uidvalidity: int, last_uid: int, imported_at: str
    ) -> None:
        db.update_mailbox_state(self._c, mailbox_id, uidvalidity, last_uid, imported_at)

    def list_mailboxes_with_counts(self) -> list[Row]:
        return db.list_mailboxes_with_counts(self._c)

    # -- Mails ------------------------------------------------------------
    def insert_email(self, **fields: Any) -> bool:
        return db.insert_email(self._c, **fields)

    def count_pending_index(self, reindex: bool) -> int:
        return db.count_pending_index(self._c, reindex)

    def iter_emails_for_index(self, reindex: bool) -> Iterator[Row]:
        return db.iter_emails_for_index(self._c, reindex)

    def mark_indexed(self, email_ids: list[int], indexed_at: str) -> None:
        db.mark_indexed(self._c, email_ids, indexed_at)

    def get_raw_by_ref(self, mailbox: str, uidvalidity: int, uid: int) -> Row | None:
        return db.get_raw_by_ref(self._c, mailbox, uidvalidity, uid)

    def get_raw_by_message_id(self, message_id: str) -> Row | None:
        return db.get_raw_by_message_id(self._c, message_id)

    def fetch_email_stats_rows(self) -> list[Row]:
        return db.fetch_email_stats_rows(self._c)
