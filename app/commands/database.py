import typer

from app.config import settings
from app.storage import get_storage

app = typer.Typer(help="Datenbank verwalten")


@app.command("init")
def init() -> None:
    """Legt die Datenablage und das Schema an (idempotent)."""
    # Das Betreten des Storage-Kontexts stellt Ablage + Schema sicher
    # (SqliteStorage: Datei + Tabellen; künftige Backends analog).
    with get_storage():
        pass
    typer.echo(f"Schema in {settings.DB_PATH} angelegt/aktualisiert.")
