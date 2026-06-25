"""Read-only IMAP-Zugriff. Es werden ausschließlich lesende Befehle verwendet."""

import ssl
from contextlib import contextmanager
from collections.abc import Iterator

from imapclient import IMAPClient

from app.config import settings


def _ssl_context() -> ssl.SSLContext | None:
    """Liefert einen SSL-Context. Bei deaktivierter Prüfung werden Hostname-
    Mismatch und ungültige Zertifikatskette bewusst ignoriert."""
    if not settings.IMAP_SSL:
        return None
    ctx = ssl.create_default_context()
    if not settings.IMAP_SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


@contextmanager
def imap_session() -> Iterator[IMAPClient]:
    client = IMAPClient(
        settings.IMAP_HOST,
        port=settings.IMAP_PORT,
        ssl=settings.IMAP_SSL,
        ssl_context=_ssl_context(),
    )
    try:
        client.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        yield client
    finally:
        try:
            client.logout()
        except Exception:
            pass


def list_folders(client: IMAPClient) -> list[str]:
    return [name for _flags, _sep, name in client.list_folders()]


def examine(client: IMAPClient, folder: str) -> int:
    """Öffnet den Ordner READ-ONLY (EXAMINE) und liefert die UIDVALIDITY zurück."""
    info = client.select_folder(folder, readonly=True)
    return info[b"UIDVALIDITY"]


def search_new_uids(client: IMAPClient, last_uid: int) -> list[int]:
    """UIDs, die seit dem letzten Import neu sind (> last_uid). last_uid=0 => alle."""
    if last_uid <= 0:
        return sorted(client.search("ALL"))
    # IMAP: "n:*" liefert immer auch die höchste UID mit, selbst wenn sie < n ist.
    # Deshalb hier zusätzlich strikt auf uid > last_uid filtern.
    uids = client.search(["UID", f"{last_uid + 1}:*"])
    return sorted(u for u in uids if u > last_uid)
