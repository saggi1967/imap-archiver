"""Abstraktes Storage-Backend: eine Schnittstelle, mehrere Implementierungen.

`SqliteStorage` (lokal, Default) und `RestStorage` (zentraler Service) erfüllen
dieses Protokoll. Alle Aufrufer sprechen nur noch ``storage.…`` — der Wechsel
zwischen lokaler SQLite und zentralem REST-Service ist eine reine Config-Frage
(``STORAGE_BACKEND``, siehe VORSCHLAG-zentrale-speicherung.md).

Benutzung immer als Kontextmanager, damit Verbindung/Transaktion (SQLite) bzw.
HTTP-Client (REST) sauber auf- und abgebaut werden::

    with get_storage() as storage:
        storage.store_email_batch(mb_id, "INBOX", uidv, batch)
        storage.commit()
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

# Eine Ergebniszeile ist Mapping-artig (SQLite: sqlite3.Row, REST: dict) — beide
# unterstützen row["spalte"]. Aufrufer greifen ausschließlich per Schlüssel zu.
Row = Mapping[str, Any]


@dataclass
class StatsSummary:
    """Aggregierte Statistik — bei SQLite lokal berechnet, bei REST vom Server."""

    total: int = 0
    total_size: int = 0
    span_start: datetime | None = None
    span_end: datetime | None = None
    distinct_senders: int = 0
    per_year: dict[int, int] = field(default_factory=dict)
    per_month: dict[int, int] = field(default_factory=dict)
    per_weekday: dict[int, int] = field(default_factory=dict)
    top_senders: list[tuple[str, int]] = field(default_factory=list)


class StorageBackend(Protocol):
    """Vertragspunkt für alle Persistenz-Operationen der CLI."""

    # -- Sitzungs-/Transaktions-Lebenszyklus ------------------------------
    def __enter__(self) -> "StorageBackend": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None: ...
    def commit(self) -> None:
        """Zwischen-Commit (SQLite: Transaktion; REST: no-op, da HTTP atomar)."""
        ...

    # -- Ordner (mailbox) -------------------------------------------------
    def get_mailbox(self, name: str) -> Row | None: ...
    def upsert_mailbox(self, name: str) -> int: ...
    def reset_mailbox_state(self, mailbox_id: int, uidvalidity: int) -> None: ...
    def reset_mailbox_full(self, mailbox_id: int) -> None: ...
    def update_mailbox_state(
        self, mailbox_id: int, uidvalidity: int, last_uid: int, imported_at: str
    ) -> None: ...
    def list_mailboxes_with_counts(self) -> list[Row]: ...

    # -- Mails (email) ----------------------------------------------------
    def store_email_batch(
        self,
        mailbox_id: int,
        mailbox_name: str,
        uidvalidity: int,
        emails: list[dict],
    ) -> tuple[int, int]:
        """Persistiert einen Batch Mails idempotent. Gibt (inserted, skipped) zurück.

        Jede ``emails``-Zeile enthält die Felder uid, uidvalidity, message_id,
        from_addr, to_addr, subject, date_header, internaldate, size, raw (bytes).
        SQLite: lokale Schleife in einer Transaktion. REST: ein async Sync-Job
        (POST /sync-jobs) plus Poll bis fertig.
        """
        ...

    def count_pending_index(self, reindex: bool) -> int: ...
    def iter_emails_for_index(self, reindex: bool) -> Iterator[Row]: ...
    def mark_indexed(self, email_ids: list[int], indexed_at: str) -> None: ...
    def get_raw_by_ref(self, mailbox: str, uidvalidity: int, uid: int) -> Row | None: ...
    def get_raw_by_message_id(self, message_id: str) -> Row | None: ...
    def stats_summary(self, top: int) -> StatsSummary: ...
