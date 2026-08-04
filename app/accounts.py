"""Client-seitiger Zugriff auf die zentralen IMAP-Konten des mailarc-servers.

Zwei Aufgaben:

* CRUD für den ``mailarc account``-Befehl (anlegen/auflisten/entfernen).
* ``ensure_account_credentials()`` — löst vor jedem IMAP-Zugriff das in
  ``settings.ACCOUNT`` gewählte Konto auf und schreibt Host/User/Passwort/Ordner
  in die laufenden ``settings``. So verbindet sich der Client wie gewohnt selbst
  read-only zum IMAP, ohne dass Zugangsdaten in der lokalen .env stehen müssen.
"""

from __future__ import annotations

import httpx

from app.config import settings


class AccountsError(RuntimeError):
    """Fachlicher Fehler beim Kontozugriff (Netz, Auth, Server-Antwort)."""


def _client() -> httpx.Client:
    if not settings.REST_API_TOKEN:
        raise AccountsError("REST_API_TOKEN ist nicht gesetzt.")
    return httpx.Client(
        base_url=settings.REST_BASE_URL.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.REST_API_TOKEN}"},
        verify=settings.REST_VERIFY_CERTS,
        timeout=settings.REST_TIMEOUT,
    )


def _raise_for(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    detail = ""
    try:
        detail = resp.json().get("detail", "")
    except Exception:  # noqa: BLE001 — Fehlertext ist best effort
        detail = resp.text
    raise AccountsError(f"Server antwortete {resp.status_code}: {detail}")


def list_accounts() -> list[dict]:
    with _client() as c:
        r = c.get("/accounts")
        _raise_for(r)
        return r.json()


def create_account(payload: dict) -> dict:
    with _client() as c:
        r = c.post("/accounts", json=payload)
        _raise_for(r)
        return r.json()


def delete_account(name: str) -> None:
    with _client() as c:
        r = c.delete(f"/accounts/{name}")
        _raise_for(r)


def update_account(name: str, payload: dict) -> dict:
    """Ändert ein bestehendes Konto teilweise (nur die übergebenen Felder).

    Der Server (mailarc-server) muss dafür ``PATCH /accounts/{name}`` anbieten;
    das Passwort wird nur überschrieben, wenn ``imap_password`` enthalten ist.
    """
    with _client() as c:
        r = c.patch(f"/accounts/{name}", json=payload)
        _raise_for(r)
        return r.json()


def get_credentials(name: str) -> dict:
    with _client() as c:
        r = c.get(f"/accounts/{name}/credentials")
        _raise_for(r)
        return r.json()


def get_config(name: str) -> dict:
    """Vollständiges Profil (IMAP + ES + Anhang). Fällt bei älterem Server, der
    ``/config`` noch nicht kennt, auf ``/credentials`` zurück (dann ohne ES-Felder).
    """
    with _client() as c:
        r = c.get(f"/accounts/{name}/config")
        if r.status_code == 404 and "config" in str(r.request.url):
            r = c.get(f"/accounts/{name}/credentials")
        _raise_for(r)
        return r.json()


# Feld → settings-Attribut für die zentral überschreibbare Zusatzkonfig. Wird nur
# angewandt, wenn der Server einen Wert liefert (None = lokalen Default behalten).
_CENTRAL_MAP = {
    "es_host": "ES_HOST",
    "es_user": "ES_USER",
    "es_password": "ES_PASSWORD",
    "es_index": "ES_INDEX",
    "es_verify_certs": "ES_VERIFY_CERTS",
    "attachment_text": "ATTACHMENT_TEXT",
    "attachment_max_bytes": "ATTACHMENT_MAX_BYTES",
    "attachment_max_chars": "ATTACHMENT_MAX_CHARS",
}

_applied = False


def ensure_central_config() -> None:
    """Überträgt das gewählte Profil (IMAP + ES + Anhang) einmalig in ``settings``.

    No-op, wenn kein Konto gewählt ist oder das REST-Backend nicht aktiv ist —
    dann gelten weiter die Werte aus der (globalen oder lokalen) .env. IMAP-Felder
    werden immer gesetzt; ES-/Anhang-Felder nur, wenn der Server sie liefert.
    """
    global _applied
    if _applied or not settings.ACCOUNT or settings.STORAGE_BACKEND != "rest":
        return
    cfg = get_config(settings.ACCOUNT)
    settings.IMAP_HOST = cfg["imap_host"]
    settings.IMAP_PORT = cfg["imap_port"]
    settings.IMAP_SSL = cfg["imap_ssl"]
    settings.IMAP_SSL_VERIFY = cfg["imap_ssl_verify"]
    settings.IMAP_USER = cfg["imap_user"]
    settings.IMAP_PASSWORD = cfg["imap_password"]
    settings.IMAP_FOLDERS = cfg["folders"]
    for key, attr in _CENTRAL_MAP.items():
        value = cfg.get(key)
        if value is not None:
            setattr(settings, attr, value)
    _applied = True


# Rückwärtskompatibler Name für bestehende Aufrufer (imap.py, commands/sync.py):
# lädt jetzt das komplette Profil, nicht mehr nur die IMAP-Credentials.
def ensure_account_credentials() -> None:
    ensure_central_config()
