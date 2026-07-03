"""Auswahl des Storage-Backends über ``settings.STORAGE_BACKEND``.

- ``sqlite`` (Default): lokale SQLite-Datei.
- ``rest``: zentraler mailarc-server (Vorschlag Phase 3/4).
"""

from app.config import settings
from app.storage.base import Row, StatsSummary, StorageBackend
from app.storage.sqlite import SqliteStorage

__all__ = ["Row", "StatsSummary", "StorageBackend", "SqliteStorage", "get_storage"]


def get_storage() -> StorageBackend:
    """Liefert das konfigurierte Storage-Backend."""
    backend = settings.STORAGE_BACKEND.strip().lower()
    if backend == "sqlite":
        return SqliteStorage(settings.DB_PATH)
    if backend == "rest":
        # Lazy-Import: httpx nur laden, wenn REST wirklich genutzt wird.
        from app.storage.rest import RestStorage

        return RestStorage(
            base_url=settings.REST_BASE_URL,
            token=settings.REST_API_TOKEN,
            verify=settings.REST_VERIFY_CERTS,
            timeout=settings.REST_TIMEOUT,
        )
    raise ValueError(
        f"Unbekanntes STORAGE_BACKEND: {settings.STORAGE_BACKEND!r} (sqlite|rest)"
    )
