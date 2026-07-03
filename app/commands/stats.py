import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.storage import get_storage

app = typer.Typer(help="Statistiken zu den geladenen Mails")
console = Console()

_WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


def _bar(value: int, maxv: int, width: int = 32, style: str = "cyan") -> str:
    filled = round(width * value / maxv) if maxv else 0
    return f"[{style}]{'█' * filled}[/][dim]{'░' * (width - filled)}[/]"


def _color_scale(value: int, maxv: int) -> str:
    """Farbe je nach relativer Höhe: wenig=blau … viel=rot."""
    r = value / maxv if maxv else 0
    if r >= 0.8:
        return "bold red"
    if r >= 0.5:
        return "yellow"
    if r >= 0.25:
        return "green"
    return "cyan"


_EP_STATS = (
    "Beispiele:\n\n\b\n"
    "mailarc stats show\n"
    "mailarc stats show -n 20   # Top 20 Absender"
)


@app.command("show", epilog=_EP_STATS)
def show(
    top: int = typer.Option(10, "--top", "-n", help="Anzahl Top-Absender / größte Mails."),
) -> None:
    """Zeigt farbige Statistiken (Jahre, Absender, Wochentage, Größen …)."""
    with get_storage() as storage:
        s = storage.stats_summary(top)

    if s.total == 0:
        console.print("[yellow]Keine Mails in der Datenbank. Erst `mailarc sync run` ausführen.[/]")
        return

    # ── Übersicht ────────────────────────────────────────────────────────────
    span = ""
    if s.span_start and s.span_end:
        span = f"{s.span_start:%d.%m.%Y} – {s.span_end:%d.%m.%Y}"
    overview = (
        f"[bold]Mails gesamt:[/]   [green]{s.total:,}[/]\n"
        f"[bold]Gesamtgröße:[/]    [cyan]{_human(s.total_size)}[/]\n"
        f"[bold]Ø Größe:[/]        {_human(s.total_size // max(s.total, 1))}\n"
        f"[bold]Zeitraum:[/]       {span or '–'}\n"
        f"[bold]Absender:[/]       [magenta]{s.distinct_senders:,}[/] verschiedene"
    ).replace(",", ".")
    console.print(Panel(overview, title="📊 Übersicht", border_style="bright_blue", expand=False))

    # ── Mails pro Jahr ───────────────────────────────────────────────────────
    if s.per_year:
        maxv = max(s.per_year.values())
        t = Table(title="Mails pro Jahr", header_style="bold magenta", expand=False)
        t.add_column("Jahr", style="bold")
        t.add_column("Anzahl", justify="right")
        t.add_column("Verteilung", ratio=1)
        for year in sorted(s.per_year):
            cnt = s.per_year[year]
            t.add_row(
                str(year),
                f"[{_color_scale(cnt, maxv)}]{cnt}[/]",
                _bar(cnt, maxv, style=_color_scale(cnt, maxv)),
            )
        console.print(t)

    # ── Top-Absender ─────────────────────────────────────────────────────────
    if s.top_senders:
        maxs = s.top_senders[0][1]
        t = Table(title=f"Top {top} Absender", header_style="bold magenta", expand=False)
        t.add_column("Absender", style="cyan", no_wrap=True)
        t.add_column("Mails", justify="right")
        t.add_column("Anteil", justify="right", style="dim")
        for addr, cnt in s.top_senders:
            t.add_row(addr, f"[{_color_scale(cnt, maxs)}]{cnt}[/]", f"{cnt / s.total * 100:.1f} %")
        console.print(t)

    # ── Wochentage ───────────────────────────────────────────────────────────
    if s.per_weekday:
        maxw = max(s.per_weekday.values())
        t = Table(title="Verteilung nach Wochentag", header_style="bold magenta", expand=False)
        t.add_column("Tag", style="bold")
        t.add_column("Anzahl", justify="right")
        t.add_column("Verteilung", ratio=1)
        for d in range(7):
            cnt = s.per_weekday.get(d, 0)
            t.add_row(_WEEKDAYS[d], str(cnt), _bar(cnt, maxw, style=_color_scale(cnt, maxw)))
        console.print(t)

    # ── Aktivste Monate (alle Jahre zusammengefasst) ─────────────────────────
    if s.per_month:
        maxm = max(s.per_month.values())
        t = Table(title="Verteilung nach Monat", header_style="bold magenta", expand=False)
        t.add_column("Monat", style="bold")
        t.add_column("Anzahl", justify="right")
        t.add_column("Verteilung", ratio=1)
        for m in range(1, 13):
            cnt = s.per_month.get(m, 0)
            t.add_row(_MONTHS[m - 1], str(cnt), _bar(cnt, maxm, style=_color_scale(cnt, maxm)))
        console.print(t)
