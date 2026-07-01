import typer

from app.imap import imap_session, list_folders
from app.storage import get_storage

app = typer.Typer(help="Status und Ordnerübersicht")


@app.command("show")
def show() -> None:
    """Zeigt pro Ordner den Sync-Stand und die Anzahl gespeicherter Mails."""
    with get_storage() as storage:
        rows = storage.list_mailboxes_with_counts()

    if not rows:
        typer.echo("Noch keine Ordner importiert.")
        return

    for r in rows:
        typer.echo(
            f"{r['name']}: {r['cnt']} Mails, last_uid={r['last_uid']}, "
            f"uidvalidity={r['uidvalidity']}, letzter Import: {r['last_import_at'] or '-'}"
        )


@app.command("folders")
def folders() -> None:
    """Listet die auf dem IMAP-Server verfügbaren Ordner."""
    with imap_session() as client:
        for name in list_folders(client):
            typer.echo(name)
