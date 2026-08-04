"""Such-Client speziell für den E-Mail-Index in Elasticsearch."""

import json as jsonlib
import re
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app import es, extract
from app.config import settings
from app.storage import get_storage

_MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
_WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Der Modus wird vom Root-Typer (main.py) gesteuert: rich_markup_mode=None,
# damit \b die Zeilenumbrüche der Beispiel-Epiloge in --help erhält.
app = typer.Typer(
    help="E-Mails in Elasticsearch durchsuchen",
    epilog=(
        "Beispiele:\n\n\b\n"
        "mailarc search query \"Angebot Gebühren\"\n"
        "mailarc search query --from chef@firma.de --last 7d\n"
        "mailarc search count rechnung --last 30d\n"
        "mailarc search show INBOX:7:42\n"
        "mailarc search top --by from_domain"
    ),
)
console = Console()

_EP_QUERY = (
    "Beispiele:\n\n\b\n"
    "# Volltext über Betreff, Body und Absender\n"
    "mailarc search query \"Angebot Gebühren\"\n"
    "# Suchwort + Absender-Domain\n"
    "mailarc search query rechnung --domain firma.de\n"
    "# fester Absender, letzte 7 Tage\n"
    "mailarc search query --from chef@firma.de --last 7d\n"
    "# nur im Betreff und nur Mails mit Anhang\n"
    "mailarc search query -s Protokoll --attachments\n"
    "# exakte Phrase (Tokens direkt aufeinander), z. B. eine Belegnummer\n"
    "mailarc search query \"26/130\" --phrase\n"
    "# Anhang-Dateiname + Zeitraum, als JSON\n"
    "mailarc search query --file .pdf --since 2026-01-01 --json"
)

_EP_COUNT = (
    "Beispiele:\n\n\b\n"
    "mailarc search count rechnung --last 30d\n"
    "mailarc search count --domain firma.de"
)

_EP_SHOW = (
    "Beispiele:\n\n\b\n"
    "mailarc search show INBOX:7:42\n"
    "mailarc search show \"<abc@firma.de>\""
)

_EP_TOP = (
    "Beispiele:\n\n\b\n"
    "mailarc search top --by from_domain\n"
    "mailarc search top --by from_addr -n 25\n"
    "mailarc search top --by mailbox"
)

_EP_RECENT = (
    "Beispiele:\n\n\b\n"
    "# die 25 neuesten Mails (Default)\n"
    "mailarc search recent\n"
    "# mehr anzeigen\n"
    "mailarc search recent -n 100\n"
    "# nur die letzten 7 Tage\n"
    "mailarc search recent --last 7d\n"
    "# Zeitraum + Ordner, ohne Vorschautext\n"
    "mailarc search recent --since 2026-06-01 --mailbox INBOX --no-preview"
)

_EP_DOWNLOAD = (
    "Beispiele:\n\n\b\n"
    "# alle Anhänge einer Mail ins aktuelle Verzeichnis\n"
    "mailarc search download INBOX:7:42\n"
    "# in ein Zielverzeichnis\n"
    "mailarc search download INBOX:7:42 -o ~/Downloads\n"
    "# nur den 2. Anhang\n"
    "mailarc search download INBOX:7:42 -i 2\n"
    "# auch per Message-ID auflösbar\n"
    "mailarc search download \"<abc@firma.de>\""
)

_EP_PDF = (
    "Beispiele:\n\n\b\n"
    "# HTML-Mail als PDF ins aktuelle Verzeichnis (Name aus Betreff)\n"
    "mailarc search pdf INBOX:7:42\n"
    "# fester Dateiname\n"
    "mailarc search pdf INBOX:7:42 -o ~/Rechnung.pdf\n"
    "# in ein Zielverzeichnis und danach öffnen\n"
    "mailarc search pdf INBOX:7:42 -o ~/Desktop --open\n"
    "# externe Bilder (http/https) mitladen — Standard ist blockiert\n"
    "mailarc search pdf \"<abc@firma.de>\" --load-remote"
)

_EP_PDF_BATCH = (
    "Beispiele:\n\n\b\n"
    "# alle Treffer einer Suche als PDF; Schema <prefix>_<datum>[_lfdnr].pdf\n"
    "mailarc search pdf-batch --from rechnung@apple.com -p Apple_Rechnung -o ~/Rechnungen\n"
    "# Volltext + Domain + Zeitraum\n"
    "mailarc search pdf-batch Rechnung --domain apple.com --since 2026-01-01 -p Apple_Rechnung\n"
    "# nur ein Ordner, externe Bilder mitladen\n"
    "mailarc search pdf-batch --mailbox INBOX -p Apple --load-remote"
)


def _human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} GB"


def _safe_name(name: str | None, idx: int) -> str:
    base = Path(name or "").name  # Pfadanteile entfernen
    base = re.sub(r"[^\w.\-() ]", "_", base).strip(" .")
    return base or f"anhang-{idx}.bin"


def _require_render():
    """Lädt das render-Modul und stellt sicher, dass WeasyPrint verfügbar ist.

    Im macOS-Paket sind die nativen WeasyPrint-Libs bewusst nicht gebündelt; dann
    fehlt hier eine klare Meldung statt eines Stacktraces mitten im Rendern.
    """
    from app import render

    if not render.WEASYPRINT_OK:
        console.print(
            "[red]PDF-Export nicht verfügbar:[/] WeasyPrint fehlt "
            f"[dim]({render.WEASYPRINT_ERROR})[/].\n"
            "  Installation:  pip install weasyprint  ·  brew install pango  # native Libs (macOS)"
        )
        raise typer.Exit(1)
    return render


def _unique_path(path: Path) -> Path:
    """Hängt bei Namenskollision " (n)" an, statt zu überschreiben."""
    if not path.exists():
        return path
    i = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def _pdf_filename(subject: str | None, doc_id: str) -> str:
    """Leitet einen sicheren PDF-Dateinamen aus dem Betreff (Fallback: ID) ab."""
    base = re.sub(r"[^\w.\-() ]", "_", subject or doc_id).strip(" .")
    return (base[:120] or "mail") + ".pdf"


def _parse_last(last: str) -> str:
    """'7d' / '24h' / '30m' → ISO-Zeitpunkt 'jetzt minus X' für eine date-Range."""
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    unit = last[-1].lower()
    if unit not in units or not last[:-1].isdigit():
        raise typer.BadParameter("Format: z. B. 24h, 7d, 30m, 2w")
    delta = timedelta(**{units[unit]: int(last[:-1])})
    return (datetime.now() - delta).isoformat()


def build_query(
    text: str | None,
    frm: str | None,
    to: str | None,
    domain: str | None,
    subject: str | None,
    file: str | None,
    mailbox: str | None,
    has_attachment: bool | None,
    since: str | None,
    until: str | None,
    phrase: bool = False,
) -> dict:
    must: list[dict] = []
    filt: list[dict] = []

    if text:
        must.append(
            {
                "multi_match": {
                    "query": text,
                    "fields": ["subject^3", "from_name^2", "body", "attachment_text"],
                    # phrase: Tokens müssen direkt aufeinanderfolgen (z. B. "26/130"),
                    # statt best_fields, das einzelne Tokens per OR matcht.
                    "type": "phrase" if phrase else "best_fields",
                }
            }
        )
    if subject:
        must.append({"match": {"subject": subject}})
    if file:
        must.append(
            {
                "nested": {
                    "path": "attachments",
                    "query": {"match": {"attachments.filename": file}},
                }
            }
        )
    if frm:
        filt.append({"term": {"from_addr": frm.lower()}})
    if to:
        filt.append({"term": {"to": to.lower()}})
    if domain:
        filt.append({"term": {"from_domain": domain.lower()}})
    if mailbox:
        filt.append({"term": {"mailbox": mailbox}})
    if has_attachment is not None:
        filt.append({"term": {"has_attachment": has_attachment}})

    rng: dict = {}
    if since:
        rng["gte"] = since
    if until:
        rng["lte"] = until
    if rng:
        filt.append({"range": {"date": rng}})

    if not must and not filt:
        return {"match_all": {}}
    return {"bool": {"must": must or [{"match_all": {}}], "filter": filt}}


def _fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value[:16]


def _fmt_inbox_date(value: str | None, now: datetime) -> str:
    """Kompaktes Datum wie in einem Mail-Client: heute → Uhrzeit, sonst Datum."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return value[:10]
    if dt.date() == now.date():
        return f"Heute {dt:%H:%M}"
    if dt.year == now.year:
        return f"{_WEEKDAYS[dt.weekday()]} {dt.day:02d}. {_MONTHS[dt.month - 1]} {dt:%H:%M}"
    return dt.strftime("%d.%m.%Y")


def _preview(text: str | None, length: int = 90) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat[:length] + ("…" if len(flat) > length else "")


@app.command("query", epilog=_EP_QUERY)
def query(
    text: str = typer.Argument(None, help="Volltext über Betreff, Body und Absendername."),
    frm: str = typer.Option(None, "--from", help="Exakte Absenderadresse."),
    to: str = typer.Option(None, "--to", help="Exakte Empfängeradresse."),
    domain: str = typer.Option(None, "--domain", help="Absender-Domain, z. B. firma.de."),
    subject: str = typer.Option(None, "--subject", "-s", help="Nur im Betreff suchen."),
    phrase: bool = typer.Option(
        False, "--phrase", "-x", help="Exakte Phrase: Tokens müssen direkt aufeinanderfolgen (z. B. 26/130)."
    ),
    file: str = typer.Option(None, "--file", help="Anhang-Dateiname (Teilwort)."),
    mailbox: str = typer.Option(None, "--mailbox", help="Auf einen IMAP-Ordner einschränken."),
    attachments: bool = typer.Option(
        None, "--attachments/--no-attachments", help="Nur Mails mit/ohne Anhang."
    ),
    since: str = typer.Option(None, "--since", help="Ab Datum (YYYY-MM-DD)."),
    until: str = typer.Option(None, "--until", help="Bis Datum (YYYY-MM-DD)."),
    last: str = typer.Option(None, "--last", help="Relativ, z. B. 24h, 7d, 2w."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max. Treffer (Default 50)."),
    json_out: bool = typer.Option(False, "--json", help="Rohe Treffer als JSON ausgeben."),
) -> None:
    """Durchsucht den E-Mail-Index und zeigt die Treffer als Tabelle."""
    since_iso = since
    if last:
        since_iso = _parse_last(last)

    q = build_query(
        text, frm, to, domain, subject, file, mailbox, attachments, since_iso, until, phrase
    )
    client = es.client()
    resp = client.search(
        index=settings.ES_INDEX,
        query=q,
        size=limit,
        sort=[{"date": {"order": "desc", "missing": "_last"}}],
        highlight={
            "fields": {
                "body": {"fragment_size": 120, "number_of_fragments": 1},
                "attachment_text": {"fragment_size": 120, "number_of_fragments": 1},
            }
        },
        source_excludes=["body", "attachment_text"],
    )

    hits = resp["hits"]["hits"]
    total = resp["hits"]["total"]["value"]

    if json_out:
        console.print_json(jsonlib.dumps(hits))
        return

    if not hits:
        console.print("[yellow]Keine Treffer.[/]")
        return

    table = Table(
        title=f"{total} Treffer (zeige {len(hits)})", header_style="bold magenta", expand=True
    )
    table.add_column("ID", style="yellow", no_wrap=True)
    table.add_column("Datum", style="cyan", no_wrap=True)
    table.add_column("Von", style="green", no_wrap=True)
    table.add_column("Betreff/Auszug")
    table.add_column("📎", justify="center")
    for h in hits:
        src = h["_source"]
        subj = src.get("subject") or "[dim](kein Betreff)[/]"
        snippet = ""
        hl = h.get("highlight", {})
        if hl.get("body"):
            frag = hl["body"][0].replace("\n", " ")
            snippet = f"\n[dim]{frag}[/]"
        elif hl.get("attachment_text"):
            frag = hl["attachment_text"][0].replace("\n", " ")
            snippet = f"\n[dim]📎 {frag}[/]"
        att = f"[yellow]{src.get('attachment_count')}[/]" if src.get("has_attachment") else ""
        table.add_row(
            h["_id"],
            _fmt_date(src.get("date")),
            src.get("from_addr") or "—",
            subj + snippet,
            att,
        )
    console.print(table)
    console.print("[dim]ID für Details: mailarc search show <ID>[/]")


@app.command("count", epilog=_EP_COUNT)
def count(
    text: str = typer.Argument(None),
    frm: str = typer.Option(None, "--from"),
    domain: str = typer.Option(None, "--domain"),
    mailbox: str = typer.Option(None, "--mailbox"),
    since: str = typer.Option(None, "--since"),
    until: str = typer.Option(None, "--until"),
    last: str = typer.Option(None, "--last"),
    phrase: bool = typer.Option(
        False, "--phrase", "-x", help="Exakte Phrase: Tokens müssen direkt aufeinanderfolgen."
    ),
) -> None:
    """Zählt Treffer, ohne sie auszugeben."""
    since_iso = _parse_last(last) if last else since
    q = build_query(text, frm, None, domain, None, None, mailbox, None, since_iso, until, phrase)
    client = es.client()
    n = client.count(index=settings.ES_INDEX, query=q)["count"]
    console.print(f"[bold green]{n}[/] Treffer")


@app.command("show", epilog=_EP_SHOW)
def show(
    doc_id: str = typer.Argument(..., help="Dokument-ID (mailbox:uidvalidity:uid) oder Message-ID."),
) -> None:
    """Zeigt eine einzelne Mail vollständig (inkl. Body und Anhängen)."""
    client = es.client()
    src = None
    if client.exists(index=settings.ES_INDEX, id=doc_id):
        src = client.get(index=settings.ES_INDEX, id=doc_id)["_source"]
    else:
        resp = client.search(
            index=settings.ES_INDEX, query={"term": {"message_id": doc_id}}, size=1
        )
        if resp["hits"]["hits"]:
            src = resp["hits"]["hits"][0]["_source"]

    if not src:
        console.print(f"[red]Keine Mail zu '{doc_id}' gefunden.[/]")
        raise typer.Exit(1)

    header = (
        f"[bold]Von:[/]      {src.get('from_name') or ''} <{src.get('from_addr') or '—'}>\n"
        f"[bold]An:[/]       {', '.join(src.get('to') or []) or '—'}\n"
        f"[bold]Cc:[/]       {', '.join(src.get('cc') or []) or '—'}\n"
        f"[bold]Datum:[/]    {_fmt_date(src.get('date'))}\n"
        f"[bold]Ordner:[/]   {src.get('mailbox')}   [dim]uid={src.get('uid')}[/]\n"
        f"[bold]Betreff:[/]  [cyan]{src.get('subject') or '(kein Betreff)'}[/]"
    )
    console.print(Panel(header, border_style="bright_blue", expand=False))

    if src.get("attachments"):
        t = Table(title="Anhänge", header_style="bold magenta")
        t.add_column("Datei")
        t.add_column("Typ")
        t.add_column("Größe", justify="right")
        for a in src["attachments"]:
            t.add_row(a.get("filename") or "—", a.get("content_type") or "—", str(a.get("size")))
        console.print(t)

    console.print(Panel(src.get("body") or "[dim](kein Text)[/]", title="Body", border_style="dim"))


@app.command("recent", epilog=_EP_RECENT)
def recent(
    limit: int = typer.Option(25, "--limit", "-n", help="Anzahl Mails (Default 25)."),
    last: str = typer.Option(None, "--last", help="Nur Zeitraum, z. B. 24h, 7d, 2w."),
    since: str = typer.Option(None, "--since", help="Ab Datum (YYYY-MM-DD)."),
    until: str = typer.Option(None, "--until", help="Bis Datum (YYYY-MM-DD)."),
    mailbox: str = typer.Option(None, "--mailbox", help="Auf einen IMAP-Ordner einschränken."),
    frm: str = typer.Option(None, "--from", help="Nur von dieser Absenderadresse."),
    domain: str = typer.Option(None, "--domain", help="Nur von dieser Absender-Domain."),
    preview: bool = typer.Option(True, "--preview/--no-preview", help="Vorschautext anzeigen."),
    json_out: bool = typer.Option(False, "--json", help="Rohe Treffer als JSON ausgeben."),
) -> None:
    """Quickview: die neuesten Mails im Mail-Client-Stil (nach Datum absteigend)."""
    since_iso = _parse_last(last) if last else since
    q = build_query(None, frm, None, domain, None, None, mailbox, None, since_iso, until)

    client = es.client()
    includes = ["date", "from_addr", "from_name", "subject", "mailbox", "uid", "uidvalidity",
                "has_attachment", "attachment_count"]
    if preview:
        includes.append("body")
    resp = client.search(
        index=settings.ES_INDEX,
        query=q,
        size=limit,
        sort=[{"date": {"order": "desc", "missing": "_last"}}],
        source_includes=includes,
    )
    hits = resp["hits"]["hits"]

    if json_out:
        console.print_json(jsonlib.dumps(hits))
        return
    if not hits:
        console.print("[yellow]Keine Mails gefunden.[/]")
        return

    now = datetime.now()
    table = Table(
        title="📥 Neueste Mails", box=box.SIMPLE_HEAVY, header_style="bold magenta",
        expand=True, padding=(0, 1),
    )
    table.add_column("ID", style="yellow", no_wrap=True)
    table.add_column("Datum", style="cyan", no_wrap=True)
    table.add_column("Von", style="green", no_wrap=True, max_width=30, overflow="ellipsis")
    table.add_column("Betreff", ratio=1)
    table.add_column("📎", justify="center", no_wrap=True)
    for h in hits:
        src = h["_source"]
        sender = src.get("from_name") or src.get("from_addr") or "—"
        subject = src.get("subject") or "[dim](kein Betreff)[/]"
        if preview and src.get("body"):
            subject += f"\n[dim]{_preview(src['body'])}[/]"
        att = f"[yellow]{src.get('attachment_count')}[/]" if src.get("has_attachment") else ""
        table.add_row(h["_id"], _fmt_inbox_date(src.get("date"), now), sender, subject, att)
    console.print(table)
    console.print(
        f"[dim]{len(hits)} Mails · „mailarc search show <ID>“ für Details[/]"
    )


@app.command("download", epilog=_EP_DOWNLOAD)
def download(
    doc_id: str = typer.Argument(
        ..., help="Dokument-ID (mailbox:uidvalidity:uid) oder Message-ID."
    ),
    out: Path = typer.Option(
        Path("."), "--out", "-o", help="Zielverzeichnis (wird bei Bedarf angelegt)."
    ),
    index: int = typer.Option(
        None, "--index", "-i", help="Nur diesen Anhang (1-basiert) speichern."
    ),
) -> None:
    """Speichert die Anhänge einer gefundenen Mail als Dateien (Quelle: lokale DB)."""
    with get_storage() as storage:
        row = None
        # Bevorzugt mailbox:uidvalidity:uid; uid/uidvalidity sind die letzten zwei Teile.
        parts = doc_id.rsplit(":", 2)
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            row = storage.get_raw_by_ref(parts[0], int(parts[1]), int(parts[2]))
        if row is None:
            row = storage.get_raw_by_message_id(doc_id)

    if row is None:
        console.print(f"[red]Keine Mail zu '{doc_id}' in der DB gefunden.[/]")
        raise typer.Exit(1)

    items = list(extract.iter_attachments(row["raw"]))
    items = [(n, ct, data) for (n, ct, data) in items if data]  # leere überspringen
    if not items:
        console.print("[yellow]Diese Mail hat keine (speicherbaren) Anhänge.[/]")
        return

    if index is not None:
        if not 1 <= index <= len(items):
            console.print(f"[red]Index {index} ungültig — Mail hat {len(items)} Anhang/Anhänge.[/]")
            raise typer.Exit(1)
        items = [items[index - 1]]

    out.mkdir(parents=True, exist_ok=True)
    table = Table(title=f"Anhänge von {doc_id}", header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Datei", style="green")
    table.add_column("Typ")
    table.add_column("Größe", justify="right")
    table.add_column("Gespeichert unter")

    for n, (name, ctype, data) in enumerate(items, start=index or 1):
        target = _unique_path(out / _safe_name(name, n))
        target.write_bytes(data)
        table.add_row(str(n), name or "—", ctype or "—", _human(len(data)), str(target))

    console.print(table)
    console.print(f"[bold green]✓[/] {len(items)} Anhang/Anhänge gespeichert.")


@app.command("pdf", epilog=_EP_PDF)
def pdf(
    doc_id: str = typer.Argument(
        ..., help="Dokument-ID (mailbox:uidvalidity:uid) oder Message-ID."
    ),
    out: Path = typer.Option(
        Path("."),
        "--out",
        "-o",
        help="Zielverzeichnis oder Ziel-Datei (endet auf .pdf).",
    ),
    load_remote: bool = typer.Option(
        False,
        "--load-remote",
        help="Extern verlinkte Bilder (http/https) mitladen. Standard: blockiert (Datenschutz).",
    ),
    open_after: bool = typer.Option(
        False, "--open", help="Das erzeugte PDF danach öffnen."
    ),
) -> None:
    """Rendert den (HTML-)Inhalt einer gefundenen Mail als PDF (Quelle: lokale DB)."""
    with get_storage() as storage:
        row = None
        parts = doc_id.rsplit(":", 2)
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            row = storage.get_raw_by_ref(parts[0], int(parts[1]), int(parts[2]))
        if row is None:
            row = storage.get_raw_by_message_id(doc_id)

    if row is None:
        console.print(f"[red]Keine Mail zu '{doc_id}' in der DB gefunden.[/]")
        raise typer.Exit(1)

    render = _require_render()

    pdf_bytes = render.html_to_pdf(row["raw"], load_remote=load_remote)
    if pdf_bytes is None:
        console.print("[yellow]Diese Mail hat keinen darstellbaren Text-/HTML-Inhalt.[/]")
        raise typer.Exit(1)

    if out.suffix.lower() == ".pdf":
        out.parent.mkdir(parents=True, exist_ok=True)
        target = _unique_path(out)
    else:
        out.mkdir(parents=True, exist_ok=True)
        target = _unique_path(out / _pdf_filename(render.subject_of(row["raw"]), doc_id))

    target.write_bytes(pdf_bytes)
    console.print(
        f"[bold green]✓[/] PDF erstellt: [cyan]{target}[/] "
        f"[dim]({_human(len(pdf_bytes))})[/]"
    )
    if not load_remote:
        console.print("[dim]Externe Bilder wurden blockiert — mit --load-remote nachladen.[/]")
    if open_after:
        typer.launch(str(target))


def _mail_date_str(src: dict) -> str:
    """Mail-Datum als YYYY-MM-DD (für den Dateinamen); Fallback 'kein-datum'."""
    raw = src.get("date") or src.get("internaldate")
    if not raw:
        return "kein-datum"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10]


@app.command("pdf-batch", epilog=_EP_PDF_BATCH)
def pdf_batch(
    text: str = typer.Argument(None, help="Volltext über Betreff, Body und Absendername."),
    prefix: str = typer.Option(
        ..., "--prefix", "-p", help="Dateinamen-Präfix, z. B. Apple_Rechnung."
    ),
    out: Path = typer.Option(
        Path("."), "--out", "-o", help="Zielverzeichnis (wird bei Bedarf angelegt)."
    ),
    frm: str = typer.Option(None, "--from", help="Exakte Absenderadresse."),
    to: str = typer.Option(None, "--to", help="Exakte Empfängeradresse."),
    domain: str = typer.Option(None, "--domain", help="Absender-Domain, z. B. apple.com."),
    subject: str = typer.Option(None, "--subject", "-s", help="Nur im Betreff suchen."),
    phrase: bool = typer.Option(
        False, "--phrase", "-x", help="Exakte Phrase: Tokens müssen direkt aufeinanderfolgen."
    ),
    file: str = typer.Option(None, "--file", help="Anhang-Dateiname (Teilwort)."),
    mailbox: str = typer.Option(None, "--mailbox", help="Auf einen IMAP-Ordner einschränken."),
    attachments: bool = typer.Option(
        None, "--attachments/--no-attachments", help="Nur Mails mit/ohne Anhang."
    ),
    since: str = typer.Option(None, "--since", help="Ab Datum (YYYY-MM-DD)."),
    until: str = typer.Option(None, "--until", help="Bis Datum (YYYY-MM-DD)."),
    last: str = typer.Option(None, "--last", help="Relativ, z. B. 24h, 7d, 2w."),
    limit: int = typer.Option(1000, "--limit", "-n", help="Max. Mails (Default 1000)."),
    load_remote: bool = typer.Option(
        False, "--load-remote", help="Externe Bilder (http/https) mitladen. Standard: blockiert."
    ),
) -> None:
    """Rendert ALLE Treffer einer Suche als PDF: <prefix>_<datum>[_lfdnr].pdf.

    Die lfd. Nummer wird nur angehängt, wenn mehrere Mails auf dasselbe Datum
    fallen (dann chronologisch/aufsteigend nummeriert).
    """
    render = _require_render()

    since_iso = _parse_last(last) if last else since
    q = build_query(
        text, frm, to, domain, subject, file, mailbox, attachments, since_iso, until, phrase
    )

    client = es.client()
    resp = client.search(
        index=settings.ES_INDEX,
        query=q,
        size=limit,
        # aufsteigend, damit die lfd. Nummer bei Datumsgleichheit chronologisch läuft
        sort=[{"date": {"order": "asc", "missing": "_last"}}, {"uid": {"order": "asc"}}],
        source_includes=["date", "internaldate", "mailbox", "uid", "uidvalidity"],
    )
    hits = resp["hits"]["hits"]
    total = resp["hits"]["total"]["value"]
    if not hits:
        console.print("[yellow]Keine Treffer — nichts zu exportieren.[/]")
        return
    if total > len(hits):
        console.print(
            f"[yellow]Hinweis:[/] {total} Treffer, exportiere die ersten {len(hits)} "
            "(--limit erhöhen)."
        )

    dated = [(_mail_date_str(h["_source"]), h) for h in hits]
    counts: dict[str, int] = {}
    for d, _h in dated:
        counts[d] = counts.get(d, 0) + 1

    out.mkdir(parents=True, exist_ok=True)
    safe_prefix = re.sub(r"[^\w.\-() ]", "_", prefix).strip(" .") or "mail"

    table = Table(
        title=f"PDF-Export: {len(hits)} Mails → {out}", header_style="bold magenta", expand=True
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Datum", style="cyan", no_wrap=True)
    table.add_column("ID", style="yellow", no_wrap=True)
    table.add_column("Datei", style="green")
    table.add_column("Status", no_wrap=True)

    per_date_idx: dict[str, int] = {}
    written = skipped = 0
    with get_storage() as storage:
        for n, (d, h) in enumerate(dated, start=1):
            doc_id = h["_id"]
            parts = doc_id.rsplit(":", 2)
            row = None
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                row = storage.get_raw_by_ref(parts[0], int(parts[1]), int(parts[2]))
            if row is None:
                row = storage.get_raw_by_message_id(doc_id)
            if row is None:
                table.add_row(str(n), d, doc_id, "—", "[red]nicht in DB[/]")
                skipped += 1
                continue

            if counts[d] > 1:
                per_date_idx[d] = per_date_idx.get(d, 0) + 1
                width = max(2, len(str(counts[d])))
                name = f"{safe_prefix}_{d}_{per_date_idx[d]:0{width}d}.pdf"
            else:
                name = f"{safe_prefix}_{d}.pdf"

            try:
                pdf_bytes = render.html_to_pdf(row["raw"], load_remote=load_remote)
            except Exception as exc:  # eine kaputte Mail darf den Lauf nicht abbrechen
                table.add_row(str(n), d, doc_id, name, f"[red]Fehler: {exc}[/]")
                skipped += 1
                continue
            if pdf_bytes is None:
                table.add_row(str(n), d, doc_id, "—", "[yellow]kein Inhalt[/]")
                skipped += 1
                continue

            target = _unique_path(out / name)
            target.write_bytes(pdf_bytes)
            table.add_row(str(n), d, doc_id, target.name, "[green]✓[/]")
            written += 1

    console.print(table)
    summary = f"[bold green]✓[/] {written} PDF(s) geschrieben"
    if skipped:
        summary += f", [yellow]{skipped} übersprungen[/]"
    console.print(summary + f" → {out}")
    if not load_remote:
        console.print("[dim]Externe Bilder blockiert — mit --load-remote nachladen.[/]")


@app.command("top", epilog=_EP_TOP)
def top(
    by: str = typer.Option("from_domain", "--by", help="Feld: from_domain, from_addr, mailbox."),
    size: int = typer.Option(15, "--size", "-n", help="Anzahl Gruppen."),
) -> None:
    """Häufigkeits-Auswertung (Aggregation) über ein keyword-Feld."""
    client = es.client()
    resp = client.search(
        index=settings.ES_INDEX,
        size=0,
        aggs={"grp": {"terms": {"field": by, "size": size}}},
    )
    buckets = resp["aggregations"]["grp"]["buckets"]
    if not buckets:
        console.print("[yellow]Keine Daten.[/]")
        return
    maxv = buckets[0]["doc_count"]
    table = Table(title=f"Top {by}", header_style="bold magenta", expand=True)
    table.add_column(by, style="cyan")
    table.add_column("Anzahl", justify="right")
    table.add_column("Verteilung", ratio=1)
    for b in buckets:
        cnt = b["doc_count"]
        bar = "█" * round(32 * cnt / maxv) if maxv else ""
        table.add_row(str(b["key"]), str(cnt), f"[cyan]{bar}[/]")
    console.print(table)
