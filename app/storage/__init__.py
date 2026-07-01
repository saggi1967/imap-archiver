"""Auswahl des Storage-Backends. Default (und aktuell einzige Implementierung): SQLite.

Phase 4 (VORSCHLAG-zentrale-speicherung.md) ergänzt hier den REST-Zweig, gesteuert
über eine Konfigurationsoption (z. B. ``STORAGE_BACKEND=rest``).
"""

from app.config import settings
from app.storage.base import Row, StorageBackend
from app.storage.sqlite import SqliteStorage

__all__ = ["Row", "StorageBackend", "SqliteStorage", "get_storage"]


def get_storage() -> StorageBackend:
    """Liefert das konfigurierte Storage-Backend (aktuell immer lokale SQLite)."""
    return SqliteStorage(settings.DB_PATH)
