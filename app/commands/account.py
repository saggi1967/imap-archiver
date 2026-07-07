"""Zentrale IMAP-Konten verwalten (nur mit STORAGE_BACKEND=rest sinnvoll).

Die Zugangsdaten werden interaktiv erfragt und an den mailarc-server geschickt,
der das Passwort verschlüsselt ablegt. Danach genügt in der Client-.env
``ACCOUNT=<label>`` — Host/User/Passwort landen nicht mehr lokal auf der Platte.
"""

import typer
from rich.console import Console
from rich.table import Table

from app import accounts
from app.config import settings

app = typer.Typer(help="Zentrale IMAP-Konten anlegen/auflisten/entfernen")
console = Console()


def _require_rest() -> None:
    if settings.STORAGE_BACKEND != "rest":
        console.print(
            "[yellow]Hinweis:[/] Konten liegen im zentralen mailarc-server. "
            "Setze [cyan]STORAGE_BACKEND=rest[/] samt REST_BASE_URL/REST_API_TOKEN."
        )
        raise typer.Exit(1)


@app.command("add")
def add() -> None:
    """Legt interaktiv ein neues zentrales IMAP-Konto an (Passwort verdeckt)."""
    _require_rest()

    name = typer.prompt("Label (Kontoname)")
    imap_host = typer.prompt("IMAP-Host")
    imap_port = typer.prompt("IMAP-Port", default=993, type=int)
    imap_ssl = typer.confirm("SSL/TLS verwenden?", default=True)
    imap_ssl_verify = typer.confirm("Zertifikat prüfen?", default=True)
    imap_user = typer.prompt("IMAP-Benutzer")
    imap_password = typer.prompt(
        "IMAP-Passwort", hide_input=True, confirmation_prompt=True
    )
    folders = typer.prompt("Ordner (Komma-getrennt)", default="INBOX")

    payload = {
        "name": name,
        "imap_host": imap_host,
        "imap_port": imap_port,
        "imap_ssl": imap_ssl,
        "imap_ssl_verify": imap_ssl_verify,
        "imap_user": imap_user,
        "imap_password": imap_password,
        "folders": folders,
    }
    try:
        accounts.create_account(payload)
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        f"[bold green]✓[/] Konto [cyan]{name}[/] gespeichert (Passwort verschlüsselt).\n"
        f"  In der Client-.env dieses Kontos nutzen: [cyan]ACCOUNT={name}[/]"
    )


@app.command("list")
def list_() -> None:
    """Listet die zentral hinterlegten Konten (ohne Passwort)."""
    _require_rest()
    try:
        rows = accounts.list_accounts()
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc

    if not rows:
        console.print("Noch keine Konten hinterlegt.")
        return

    table = Table(title="Zentrale IMAP-Konten", header_style="bold magenta")
    table.add_column("Label", style="bold cyan")
    table.add_column("Host")
    table.add_column("Port", justify="right")
    table.add_column("Benutzer")
    table.add_column("SSL")
    table.add_column("Ordner")
    for r in rows:
        table.add_row(
            r["name"],
            r["imap_host"],
            str(r["imap_port"]),
            r["imap_user"],
            "✓" if r["imap_ssl"] else "—",
            r["folders"],
        )
    console.print(table)


@app.command("remove")
def remove(
    name: str = typer.Argument(..., help="Label des zu entfernenden Kontos"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ohne Rückfrage entfernen."),
) -> None:
    """Entfernt ein zentrales Konto (die bereits archivierten Mails bleiben)."""
    _require_rest()
    if not yes and not typer.confirm(f"Konto '{name}' wirklich entfernen?"):
        raise typer.Abort()
    try:
        accounts.delete_account(name)
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[bold green]✓[/] Konto [cyan]{name}[/] entfernt.")
