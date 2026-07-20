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


_applied = False


def ensure_account_credentials() -> None:
    """Überträgt die Zugangsdaten des gewählten Kontos einmalig in ``settings``.

    No-op, wenn kein Konto gewählt ist oder das REST-Backend nicht aktiv ist —
    dann gelten weiter die IMAP_*-Felder aus der lokalen .env.
    """
    global _applied
    if _applied or not settings.ACCOUNT or settings.STORAGE_BACKEND != "rest":
        return
    creds = get_credentials(settings.ACCOUNT)
    settings.IMAP_HOST = creds["imap_host"]
    settings.IMAP_PORT = creds["imap_port"]
    settings.IMAP_SSL = creds["imap_ssl"]
    settings.IMAP_SSL_VERIFY = creds["imap_ssl_verify"]
    settings.IMAP_USER = creds["imap_user"]
    settings.IMAP_PASSWORD = creds["imap_password"]
    settings.IMAP_FOLDERS = creds["folders"]
    _applied = True
