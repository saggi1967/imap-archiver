import typer

from app import db
from app.config import settings
from app.imap import imap_session, list_folders

app = typer.Typer(help="Status und Ordnerübersicht")


@app.command("show")
def show() -> None:
    """Zeigt pro Ordner den Sync-Stand und die Anzahl gespeicherter Mails."""
    with db.connect(settings.DB_PATH) as conn:
        db.init_schema(conn)
        rows = conn.execute(
            """
            SELECT m.name, m.uidvalidity, m.last_uid, m.last_import_at,
                   COUNT(e.id) AS cnt
            FROM mailbox m
            LEFT JOIN email e ON e.mailbox_id = m.id
            GROUP BY m.id
            ORDER BY m.name
            """
        ).fetchall()

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
