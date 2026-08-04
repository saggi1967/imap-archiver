"""``mailarc setup`` — schreibt die globale Bootstrap-Konfiguration.

Ziel: auf einem frischen System nach der Installation in einem Schritt
einsatzbereit sein. Erzeugt ``~/.config/mailarc/config.env`` mit dem Bootstrap
(``STORAGE_BACKEND=rest``, ``REST_BASE_URL``, ``REST_API_TOKEN``,
``REST_VERIFY_CERTS``, ``ACCOUNT``). Alles Weitere (IMAP/ES/Anhang) liegt zentral
je Konto im mailarc-server und wird zur Laufzeit geladen.

Interaktiv (Default) oder skriptbar über ``--non-interactive`` samt Flags.
"""

from __future__ import annotations

import os
import stat

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app import accounts
from app.config import global_bootstrap_path, settings

console = Console()


def _server_reachable(base_url: str, verify: bool) -> bool:
    """GET /health gegen den Server; True nur bei HTTP 200."""
    import httpx

    try:
        r = httpx.get(base_url.rstrip("/") + "/health", verify=verify, timeout=5.0)
        return r.status_code == 200
    except Exception:  # noqa: BLE001 — Erreichbarkeit ist best effort
        return False


def _write_config(path, base_url: str, token: str, verify: bool, account: str) -> None:
    """Schreibt config.env atomar mit 0600 (Datei) und 0700 (Verzeichnis)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    content = (
        "# Von `mailarc setup` erzeugt — globale Bootstrap-Konfiguration.\n"
        "# Gilt für alle Verzeichnisse. Alles Weitere (IMAP/ES/Anhang) liegt\n"
        "# zentral je Konto im mailarc-server (siehe `mailarc account`).\n"
        "\n"
        "STORAGE_BACKEND=rest\n"
        f"REST_BASE_URL={base_url}\n"
        f"REST_API_TOKEN={token}\n"
        f"REST_VERIFY_CERTS={'true' if verify else 'false'}\n"
        f"ACCOUNT={account}\n"
    )
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    tmp.replace(path)


def _require(value: str | None, flag: str) -> str:
    if not value:
        console.print(f"[red]{flag} ist im --non-interactive-Modus erforderlich.[/]")
        raise typer.Exit(1)
    return value


def setup(
    base_url: str = typer.Option(None, "--base-url", help="REST-Basis-URL des mailarc-servers."),
    token: str = typer.Option(None, "--token", help="REST_API_TOKEN (Bearer)."),
    account: str = typer.Option(None, "--account", help="Konto-Label (aus `account list`)."),
    verify: bool = typer.Option(
        None, "--verify/--no-verify", help="TLS-Zertifikat des Servers prüfen (Default: an)."
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Nicht nachfragen; Werte müssen als Flags kommen."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Vorhandene config.env ohne Rückfrage überschreiben."
    ),
) -> None:
    """Richtet die zentrale Konfiguration ein (schreibt ~/.config/mailarc/config.env).

    Nach `mailarc setup` ist das System einsatzbereit: Host/User/Passwort, Ordner,
    Elasticsearch-Ziel und Anhang-Optionen kommen zur Laufzeit vom Server.
    """
    path = global_bootstrap_path()
    interactive = not non_interactive

    if interactive:
        console.print(
            Panel(
                "[bold]mailarc einrichten[/]\n"
                "Ich lege die globale Konfiguration an, damit dieses System die zentralen\n"
                "Zugangsdaten vom mailarc-server nutzt — für [b]alle[/] Verzeichnisse.\n"
                f"[dim]Zieldatei: {path}[/]",
                border_style="bright_blue",
                expand=False,
            )
        )

    if path.exists() and not force:
        if non_interactive:
            console.print(f"[red]{path} existiert bereits.[/] Mit [cyan]--force[/] überschreiben.")
            raise typer.Exit(1)
        if not typer.confirm(f"{path} existiert bereits — überschreiben?", default=False):
            console.print("[yellow]Abgebrochen.[/]")
            raise typer.Exit(0)

    # --- REST-Basis-URL -----------------------------------------------------
    if base_url is None:
        base_url = _require(None, "--base-url") if non_interactive else typer.prompt(
            "REST-Basis-URL des mailarc-servers", default=settings.REST_BASE_URL
        )
    base_url = base_url.rstrip("/")

    # --- Zertifikatsprüfung -------------------------------------------------
    if verify is None:
        verify = True if non_interactive else typer.confirm(
            "TLS-Zertifikat des Servers prüfen?", default=True
        )

    # --- Token --------------------------------------------------------------
    if token is None:
        token = _require(None, "--token") if non_interactive else typer.prompt(
            "REST_API_TOKEN", hide_input=True
        )

    # --- Server prüfen ------------------------------------------------------
    reachable = _server_reachable(base_url, verify)
    if reachable:
        console.print(f"[green]✓[/] Server erreichbar: [cyan]{base_url}[/]")
    else:
        console.print(
            f"[yellow]⚠[/] Server unter [cyan]{base_url}[/] nicht erreichbar — "
            "Konfiguration wird trotzdem geschrieben."
        )

    # --- Konto wählen -------------------------------------------------------
    if account is None:
        rows: list[dict] = []
        if reachable:
            # Für den Abruf kurz die eingegebenen Werte in settings spiegeln.
            settings.REST_BASE_URL = base_url
            settings.REST_API_TOKEN = token
            settings.REST_VERIFY_CERTS = verify
            try:
                rows = accounts.list_accounts()
            except accounts.AccountsError as exc:
                console.print(f"[yellow]Konten nicht abrufbar:[/] {exc}")

        if non_interactive:
            account = _require(None, "--account")
        elif rows:
            table = Table(title="Verfügbare Konten", header_style="bold magenta")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Label", style="bold cyan")
            table.add_column("IMAP-Host")
            table.add_column("ES-Ziel")
            for i, r in enumerate(rows, 1):
                table.add_row(str(i), r["name"], r.get("imap_host") or "—", r.get("es_host") or "—")
            console.print(table)
            names = [r["name"] for r in rows]
            choice = typer.prompt("Konto (Nummer oder Label)", default=names[0])
            if choice.isdigit() and 1 <= int(choice) <= len(names):
                account = names[int(choice) - 1]
            else:
                account = choice
        else:
            account = typer.prompt(
                "Konto-Label (leer lassen, falls noch keins angelegt ist)", default=""
            )

    # --- Schreiben ----------------------------------------------------------
    _write_config(path, base_url, token, verify, account)

    console.print(
        Panel(
            f"[green]✓ Konfiguration geschrieben:[/] {path}\n"
            f"  REST_BASE_URL = {base_url}\n"
            f"  ACCOUNT       = {account or '[dim](noch keins)[/]'}\n"
            f"  Zertifikat    = {'geprüft' if verify else 'nicht geprüft'}",
            border_style="green",
            expand=False,
        )
    )
    if account:
        console.print("[dim]Prüfen:[/] mailarc account list   ·   [dim]Loslegen:[/] mailarc sync run")
    else:
        console.print(
            "[yellow]Noch kein Konto gewählt.[/] Erst anlegen: [cyan]mailarc account add[/], "
            "dann [cyan]mailarc setup[/] erneut oder ACCOUNT in der config.env eintragen."
        )
