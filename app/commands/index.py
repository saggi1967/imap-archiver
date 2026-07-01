from datetime import datetime, timezone

import typer
from elasticsearch.helpers import streaming_bulk
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

from app import es, extract
from app.config import settings
from app.storage import get_storage

app = typer.Typer(help="Mails suchoptimal nach Elasticsearch indexieren")
console = Console()


@app.command("init")
def init() -> None:
    """Legt den Elasticsearch-Index mit Mapping an (idempotent)."""
    client = es.client()
    created = es.ensure_index(client, settings.ES_INDEX)
    es.sync_mapping(client, settings.ES_INDEX)
    if created:
        console.print(f"[green]Index [bold]{settings.ES_INDEX}[/] mit Mapping angelegt.[/]")
    else:
        console.print(f"[yellow]Index [bold]{settings.ES_INDEX}[/] existiert — Mapping aktualisiert.[/]")


def _actions(storage, reindex: bool):
    """Erzeugt Bulk-Actions aus den (noch nicht) indexierten Mails."""
    for row in storage.iter_emails_for_index(reindex):
        try:
            doc = extract.extract_document(row)
        except Exception as exc:  # defekte Mail überspringen, nicht abbrechen
            console.print(f"[red]Übersprungen (id={row['id']}): {exc}[/]")
            continue
        yield {
            "_index": settings.ES_INDEX,
            "_id": extract.doc_id(row),
            "_source": doc,
            # row.id über die Pipeline durchreichen, um danach zu markieren
            "_db_id": row["id"],
        }


_EP_INDEX = (
    "Beispiele:\n\n\b\n"
    "# nur noch nicht indexierte Mails senden\n"
    "mailarc index run\n"
    "# alle Mails neu senden\n"
    "mailarc index run --reindex\n"
    "# größere Bulk-Batches\n"
    "mailarc index run --batch 1000"
)


@app.command("run", epilog=_EP_INDEX)
def run(
    reindex: bool = typer.Option(
        False, "--reindex", help="Alle Mails neu senden (nicht nur noch nicht indexierte)."
    ),
    batch: int = typer.Option(500, "--batch", help="Bulk-Batchgröße."),
) -> None:
    """Sendet noch nicht indexierte Mails an Elasticsearch. Mit --reindex alle."""
    client = es.client()
    if es.ensure_index(client, settings.ES_INDEX):
        console.print(f"[green]Index [bold]{settings.ES_INDEX}[/] neu angelegt.[/]")
    es.sync_mapping(client, settings.ES_INDEX)

    with get_storage() as storage:
        total = storage.count_pending_index(reindex)
        if total == 0:
            console.print("[green]✓[/] Nichts zu tun — alle Mails sind bereits indexiert.")
            return

        console.print(
            f"[bold]Indexierung[/] → [cyan]{settings.ES_HOST}[/] / "
            f"[cyan]{settings.ES_INDEX}[/]  ({total} Mails)\n"
        )

        progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]indexiere[/]"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("Mails"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )

        done_ids: list[int] = []
        ok = failed = 0
        # _db_id darf nicht an ES gehen → vor dem Versand abtrennen.
        id_map: dict[str, int] = {}

        def actions():
            for action in _actions(storage, reindex):
                id_map[action["_id"]] = action.pop("_db_id")
                yield action

        with progress:
            task = progress.add_task("", total=total)
            for success, info in streaming_bulk(
                client, actions(), chunk_size=batch, raise_on_error=False
            ):
                progress.update(task, advance=1)
                es_id = info.get("index", {}).get("_id")
                if success:
                    ok += 1
                    if es_id in id_map:
                        done_ids.append(id_map[es_id])
                else:
                    failed += 1
                    console.print(f"[red]Fehler {es_id}: {info}[/]")

        now = datetime.now(timezone.utc).isoformat()
        storage.mark_indexed(done_ids, now)
        storage.commit()
        client.indices.refresh(index=settings.ES_INDEX)

    console.print(f"\n[bold green]✓[/] {ok} indexiert" + (f", [red]{failed} Fehler[/]" if failed else ""))
