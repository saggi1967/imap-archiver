import typer

from app import db
from app.config import settings

app = typer.Typer(help="Datenbank verwalten")


@app.command("init")
def init() -> None:
    """Legt die SQLite-Datei und das Schema an (idempotent)."""
    with db.connect(settings.DB_PATH) as conn:
        db.init_schema(conn)
    typer.echo(f"Schema in {settings.DB_PATH} angelegt/aktualisiert.")
