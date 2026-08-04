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


@app.command("update")
def update(
    name: str = typer.Argument(..., help="Label des zu ändernden Kontos"),
    password_only: bool = typer.Option(
        False,
        "--password-only",
        "-p",
        help="Nur das Passwort ändern, alle anderen Felder unangetastet lassen.",
    ),
) -> None:
    """Ändert ein zentrales Konto (z. B. Passwortwechsel).

    Bei den Nicht-Passwort-Feldern ist der bisherige Wert vorbelegt — einfach
    Enter drücken behält ihn. Das Passwort wird nur überschrieben, wenn ein
    neues eingegeben wird (leer = unverändert).
    """
    _require_rest()
    try:
        rows = accounts.list_accounts()
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc

    current = next((r for r in rows if r["name"] == name), None)
    if current is None:
        console.print(f"[bold red]Kein Konto mit Label[/] [cyan]{name}[/] [bold red]gefunden.[/]")
        raise typer.Exit(1)

    payload: dict = {}
    if not password_only:
        payload["imap_host"] = typer.prompt("IMAP-Host", default=current["imap_host"])
        payload["imap_port"] = typer.prompt(
            "IMAP-Port", default=current["imap_port"], type=int
        )
        payload["imap_ssl"] = typer.confirm(
            "SSL/TLS verwenden?", default=bool(current.get("imap_ssl", True))
        )
        payload["imap_ssl_verify"] = typer.confirm(
            "Zertifikat prüfen?", default=bool(current.get("imap_ssl_verify", True))
        )
        payload["imap_user"] = typer.prompt("IMAP-Benutzer", default=current["imap_user"])
        payload["folders"] = typer.prompt(
            "Ordner (Komma-getrennt)", default=current["folders"]
        )

    new_password = typer.prompt(
        "Neues IMAP-Passwort (leer = unverändert)",
        hide_input=True,
        confirmation_prompt=True,
        default="",
        show_default=False,
    )
    if new_password:
        payload["imap_password"] = new_password

    if not payload:
        console.print("[yellow]Nichts zu ändern.[/]")
        raise typer.Exit(0)

    try:
        accounts.update_account(name, payload)
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc

    what = "Passwort" if password_only else "Konto"
    console.print(f"[bold green]✓[/] {what} für [cyan]{name}[/] aktualisiert.")


@app.command("config")
def config(
    name: str = typer.Argument(..., help="Label des Kontos, dessen Zentral-Config gesetzt wird."),
    from_env: bool = typer.Option(
        False,
        "--from-env",
        help="Aktuelle lokale ES_*/ATTACHMENT_*-Werte übernehmen (Migration der .env).",
    ),
    es_host: str = typer.Option(None, "--es-host", help="Elasticsearch-Basis-URL."),
    es_user: str = typer.Option(None, "--es-user", help="ES-Benutzer (Basic-Auth)."),
    es_password: str = typer.Option(
        None, "--es-password", help="ES-Passwort (verschlüsselt gespeichert). '-' = verdeckt abfragen."
    ),
    es_index: str = typer.Option(None, "--es-index", help="Ziel-Index."),
    es_verify: bool = typer.Option(
        None, "--es-verify/--no-es-verify", help="ES-Zertifikatsprüfung (nur https)."
    ),
    attachment_text: bool = typer.Option(
        None, "--attachment-text/--no-attachment-text", help="Anhang-Volltext extrahieren."
    ),
    attachment_max_bytes: int = typer.Option(
        None, "--attachment-max-bytes", help="Größere Anhänge überspringen."
    ),
    attachment_max_chars: int = typer.Option(
        None, "--attachment-max-chars", help="Extrahierten Text je Mail begrenzen."
    ),
) -> None:
    """Setzt die zentrale Zusatz-Config (ES-Ziel, Anhang-Optionen) eines Kontos.

    So liegt neben den IMAP-Daten auch der Rest der Konfiguration zentral — die
    lokale .env braucht dann nur noch den Bootstrap (REST_BASE_URL, REST_API_TOKEN,
    ACCOUNT). Mit --from-env werden die aktuell geladenen lokalen Werte übernommen;
    einzelne --es-*/--attachment-*-Optionen überschreiben sie gezielt.
    """
    _require_rest()
    try:
        rows = accounts.list_accounts()
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc
    if not any(r["name"] == name for r in rows):
        console.print(f"[bold red]Kein Konto mit Label[/] [cyan]{name}[/] [bold red]gefunden.[/]")
        raise typer.Exit(1)

    payload: dict = {}
    if from_env:
        payload.update(
            {
                "es_host": settings.ES_HOST,
                "es_user": settings.ES_USER,
                "es_index": settings.ES_INDEX,
                "es_verify_certs": settings.ES_VERIFY_CERTS,
                "attachment_text": settings.ATTACHMENT_TEXT,
                "attachment_max_bytes": settings.ATTACHMENT_MAX_BYTES,
                "attachment_max_chars": settings.ATTACHMENT_MAX_CHARS,
            }
        )
        if settings.ES_PASSWORD:  # leeres Passwort nicht zentral setzen/löschen
            payload["es_password"] = settings.ES_PASSWORD

    explicit = {
        "es_host": es_host,
        "es_user": es_user,
        "es_index": es_index,
        "es_verify_certs": es_verify,
        "attachment_text": attachment_text,
        "attachment_max_bytes": attachment_max_bytes,
        "attachment_max_chars": attachment_max_chars,
    }
    payload.update({k: v for k, v in explicit.items() if v is not None})

    if es_password == "-":
        es_password = typer.prompt("ES-Passwort", hide_input=True, confirmation_prompt=True)
    if es_password:
        payload["es_password"] = es_password

    if not payload:
        console.print(
            "[yellow]Nichts zu setzen.[/] Nutze --from-env oder einzelne --es-*/--attachment-*-Optionen."
        )
        raise typer.Exit(0)

    try:
        result = accounts.update_account(name, payload)
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc

    # Alte Server (< 2.3.0.0) kennen die Zentral-Config-Felder nicht und verwerfen
    # sie beim PATCH stillschweigend (antworten aber 200). Das würde fälschlich als
    # Erfolg durchgehen → hier am Antwort-Schema erkennen und klar melden.
    if not isinstance(result, dict) or "es_host" not in result:
        console.print(
            "[bold red]Der Server hat die Config nicht übernommen.[/] Er ist vermutlich "
            "veraltet und ignoriert die neuen Felder (benötigt [cyan]mailarc-server ≥ 2.3.0.0[/]).\n"
            "  → mailarc-server aktualisieren und neu starten, dann erneut ausführen."
        )
        raise typer.Exit(1)

    secret_note = " (ES-Passwort verschlüsselt)" if "es_password" in payload else ""
    console.print(
        f"[bold green]✓[/] Zentral-Config für [cyan]{name}[/] aktualisiert{secret_note}.\n"
        f"  Felder: {', '.join(sorted(payload))}"
    )


def _fmt_val(v) -> str:
    """Zeigt einen Config-Wert; None = zentral nicht gesetzt (Client-Default gilt)."""
    if v is None:
        return "[dim]— (nicht zentral gesetzt → lokaler Default)[/]"
    if isinstance(v, bool):
        return "[green]✓[/]" if v else "[red]✗[/]"
    if v == "":
        return "[dim](leer)[/]"
    return str(v)


@app.command("list")
def list_(
    show_secrets: bool = typer.Option(
        False,
        "--show-secrets",
        "-s",
        help="Passwörter im Klartext anzeigen (holt sie entschlüsselt vom Server).",
    ),
) -> None:
    """Zeigt alle zentral hinterlegten Konten mit ihrer vollständigen Konfiguration.

    Standardmäßig werden Passwörter maskiert (nur gesetzt/nicht gesetzt). Mit
    --show-secrets werden sie im Klartext ausgegeben — hilfreich, um z. B. einen
    ES-401 zu debuggen (falscher/fehlender ES-Zugang).
    """
    _require_rest()
    try:
        rows = accounts.list_accounts()
    except accounts.AccountsError as exc:
        console.print(f"[bold red]Fehlgeschlagen:[/] {exc}")
        raise typer.Exit(1) from exc

    if not rows:
        console.print("Noch keine Konten hinterlegt.")
        return

    for r in rows:
        # Klartext-Secrets nur bei Bedarf und nur für dieses Konto nachladen.
        cfg = {}
        if show_secrets:
            try:
                cfg = accounts.get_config(r["name"])
            except accounts.AccountsError as exc:
                console.print(f"[yellow]Secrets für {r['name']} nicht ladbar:[/] {exc}")

        imap_pw = (
            cfg.get("imap_password", "")
            if show_secrets
            else "•••••••• [dim](gesetzt)[/]"
        )
        # es_password_set stammt aus AccountOut; ältere Server liefern es evtl. nicht.
        es_set = r.get("es_password_set")
        if show_secrets:
            es_pw = cfg.get("es_password") or "[yellow]— (nicht gesetzt)[/]"
        elif es_set is True:
            es_pw = "•••••••• [dim](gesetzt)[/]"
        elif es_set is False:
            es_pw = "[yellow]— (nicht gesetzt)[/]"
        else:
            es_pw = "[dim]?[/]"

        table = Table(
            title=f"Konto: [bold cyan]{r['name']}[/]",
            header_style="bold magenta",
            title_justify="left",
            show_header=False,
        )
        table.add_column("Feld", style="bold", no_wrap=True)
        table.add_column("Wert")

        table.add_row("[bold blue]IMAP[/]", "")
        table.add_row("Host", _fmt_val(r["imap_host"]))
        table.add_row("Port", str(r["imap_port"]))
        table.add_row("SSL/TLS", _fmt_val(r["imap_ssl"]))
        table.add_row("Zert.-Prüfung", _fmt_val(r["imap_ssl_verify"]))
        table.add_row("Benutzer", _fmt_val(r["imap_user"]))
        table.add_row("Passwort", imap_pw)
        table.add_row("Ordner", _fmt_val(r["folders"]))

        table.add_row("[bold blue]Elasticsearch[/]", "")
        table.add_row("Host", _fmt_val(r.get("es_host")))
        table.add_row("Benutzer", _fmt_val(r.get("es_user")))
        table.add_row("Passwort", es_pw)
        table.add_row("Index", _fmt_val(r.get("es_index")))
        table.add_row("Zert.-Prüfung", _fmt_val(r.get("es_verify_certs")))

        table.add_row("[bold blue]Anhang[/]", "")
        table.add_row("Volltext", _fmt_val(r.get("attachment_text")))
        table.add_row("Max-Bytes", _fmt_val(r.get("attachment_max_bytes")))
        table.add_row("Max-Chars", _fmt_val(r.get("attachment_max_chars")))

        console.print(table)

    # Häufige 401-Ursache aktiv anmerken.
    partial_es = [
        r["name"] for r in rows if r.get("es_host") and r.get("es_password_set") is False
    ]
    if partial_es:
        console.print(
            "[yellow]Hinweis:[/] ES-Host gesetzt, aber kein ES-Passwort bei: "
            f"[bold]{', '.join(partial_es)}[/]. Das führt zu ES-401. Setzen mit:\n"
            "  [cyan]mailarc account config <label> --es-password -[/]"
        )


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
