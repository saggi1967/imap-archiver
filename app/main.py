import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from app import __version__
from app.commands import database, index, search, stats, status, sync

# Banner auf stderr, damit JSON-/Pipe-Ausgaben auf stdout sauber bleiben.
_err = Console(stderr=True)


def show_banner() -> None:
    body = Text()
    body.append("📬  mailarc ", style="bold cyan")
    body.append(f"v{__version__}\n", style="bold yellow")
    body.append("Read-only IMAP-Mailarchiv  →  SQLite  →  Elasticsearch\n", style="white")
    body.append("Import · Statistik · Volltextsuche · PDF-Anhänge · Download", style="dim")
    _err.print(Panel(body, border_style="bright_blue", expand=False, padding=(0, 2)))


def _version_callback(value: bool) -> None:
    if value:
        show_banner()
        raise typer.Exit()


app = typer.Typer(
    name="mailarc",
    help="Read-only Import von IMAP-Mails in eine lokale SQLite-DB.",
    no_args_is_help=True,
    # Click-Formatter (statt Rich) für die --help: erhält die Zeilenumbrüche der
    # Beispiel-Epiloge (mit \b). Der Root-Typer bestimmt den Modus für alle.
    rich_markup_mode=None,
    epilog=(
        "Typischer Ablauf:\n\n\b\n"
        "mailarc db init                  # SQLite anlegen\n"
        "mailarc status folders           # IMAP-Ordner ansehen\n"
        "mailarc sync run                 # Mails importieren (read-only)\n"
        "mailarc stats show               # Statistiken zu den Daten\n"
        "mailarc index run                # nach Elasticsearch indexieren\n"
        "mailarc search query \"Rechnung\"   # Index durchsuchen"
    ),
)


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Version anzeigen und beenden.",
    ),
) -> None:
    show_banner()


app.add_typer(database.app, name="db")
app.add_typer(sync.app, name="sync")
app.add_typer(status.app, name="status")
app.add_typer(stats.app, name="stats")
app.add_typer(index.app, name="index")
app.add_typer(search.app, name="search")

if __name__ == "__main__":
    app()
