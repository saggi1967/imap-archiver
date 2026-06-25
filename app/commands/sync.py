import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from app import db, sync
from app.config import settings

app = typer.Typer(help="Mails per IMAP importieren (read-only)")
console = Console()

_MODE_STYLE = {"initial": "cyan", "inkrement": "green", "resync": "yellow"}


def _summary(results: list[sync.FolderResult]) -> Table:
    table = Table(title="Import-Ergebnis", header_style="bold magenta", expand=True)
    table.add_column("Ordner", style="bold")
    table.add_column("Modus")
    table.add_column("Geprüft", justify="right")
    table.add_column("Neu", justify="right", style="green")
    table.add_column("Übersprungen", justify="right", style="dim")
    table.add_column("last_uid", justify="right")
    for r in results:
        style = _MODE_STYLE.get(r.mode, "white")
        table.add_row(
            r.folder,
            f"[{style}]{r.mode}[/]",
            str(r.fetched),
            str(r.inserted),
            str(r.skipped),
            str(r.last_uid),
        )
    return table


_EP_SYNC = (
    "Beispiele:\n\n\b\n"
    "# alle in IMAP_FOLDERS konfigurierten Ordner\n"
    "mailarc sync run\n"
    "# bestimmte Ordner\n"
    "mailarc sync run -f INBOX -f Sent\n"
    "# Voll-Import erzwingen\n"
    "mailarc sync run --full"
)


@app.command("run", epilog=_EP_SYNC)
def run(
    folder: list[str] = typer.Option(
        None, "--folder", "-f", help="Nur diese(n) Ordner (mehrfach). Default: aus Config."
    ),
    full: bool = typer.Option(
        False, "--full", help="Voll-Import erzwingen (Sync-Stand der Ordner zurücksetzen)."
    ),
) -> None:
    """Importiert neue Mails. Ohne vorigen Stand = Voll-Import, sonst nur Neues seit letztem Lauf."""
    folders = folder or settings.folders
    if not folders:
        console.print("[bold red]Keine Ordner konfiguriert (IMAP_FOLDERS).[/]")
        raise typer.Exit(1)

    console.print(
        f"[bold]IMAP-Import[/] von [cyan]{settings.IMAP_HOST}[/] "
        f"→ [cyan]{settings.DB_PATH}[/]  ({len(folders)} Ordner)\n"
    )

    with db.connect(settings.DB_PATH) as conn:
        db.init_schema(conn)
        if full:
            for name in folders:
                mailbox_id = db.upsert_mailbox(conn, name)
                conn.execute(
                    "UPDATE mailbox SET last_uid = 0, uidvalidity = NULL WHERE id = ?",
                    (mailbox_id,),
                )
            conn.commit()

        progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]{task.fields[folder]:<24}[/]"),
            TextColumn("{task.fields[mode]:<10}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("Mails"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )

        state: dict[str, object] = {"task": None}

        def on_start(name: str, mode: str, total: int) -> None:
            style = _MODE_STYLE.get(mode, "white")
            state["task"] = progress.add_task(
                "", folder=name, mode=f"[{style}]{mode}[/]", total=total
            )

        def on_tick(n: int) -> None:
            progress.update(state["task"], advance=n)

        with progress:
            results = sync.sync_folders(conn, folders, on_start=on_start, on_tick=on_tick)

    console.print()
    console.print(_summary(results))
    total_new = sum(r.inserted for r in results)
    console.print(f"\n[bold green]✓[/] Fertig — {total_new} neue Mail(s) gespeichert.")
