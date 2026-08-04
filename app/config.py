import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def global_bootstrap_path() -> Path:
    """Pfad der globalen Bootstrap-Datei ``~/.config/mailarc/config.env``.

    Respektiert ``$XDG_CONFIG_HOME``. Gemeinsame Quelle für das Laden (``_env_files``)
    und den Schreiber (``mailarc setup``), damit beide denselben Ort meinen.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg) if xdg else Path.home() / ".config"
    return config_home / "mailarc" / "config.env"


def _env_files() -> tuple[str, ...]:
    """Kandidaten-.env in aufsteigender Priorität (spätere überschreiben frühere).

    So genügt **eine** globale Bootstrap-Datei (``~/.config/mailarc/config.env``)
    für alle Verzeichnisse — eine projektlokale ``.env`` überschreibt sie bei
    Bedarf, ``$MAILARC_ENV`` schlägt alles. Echte Umgebungsvariablen haben ohnehin
    Vorrang vor jeder Datei. Nicht existierende Dateien ignoriert pydantic-settings.
    """
    files = [
        global_bootstrap_path(),  # globaler Bootstrap (Basis)
        Path(".env"),             # projektlokal (überschreibt global)
    ]
    if os.environ.get("MAILARC_ENV"):  # expliziter Override (höchste)
        files.append(Path(os.environ["MAILARC_ENV"]))
    return tuple(str(f) for f in files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(), env_file_encoding="utf-8", extra="ignore"
    )

    # IMAP-Verbindung zum Firmenserver
    IMAP_HOST: str = "localhost"
    IMAP_PORT: int = 993
    IMAP_SSL: bool = True
    # Zertifikatsprüfung. Auf false setzen, wenn das Server-Zertifikat einen
    # bekannten Hostname-Mismatch hat und das bewusst ignoriert werden soll.
    IMAP_SSL_VERIFY: bool = True
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""

    # Zentrales Konto (nur bei STORAGE_BACKEND=rest): Label eines auf dem Server
    # hinterlegten IMAP-Zugangs. Ist es gesetzt, holt der Client Host/User/Passwort
    # sowie die Ordnerliste vom Server statt aus den IMAP_*-Feldern hier.
    ACCOUNT: str = ""

    # Komma-getrennte Liste der zu importierenden Ordner. Default: nur Posteingang.
    IMAP_FOLDERS: str = "INBOX"

    # Pfad zur lokalen SQLite-Datei
    DB_PATH: str = "mailarc.db"

    # Storage-Backend: "sqlite" (lokal, Default) oder "rest" (zentraler mailarc-server).
    STORAGE_BACKEND: str = "sqlite"
    REST_BASE_URL: str = "http://localhost:8000"
    REST_API_TOKEN: str = ""
    REST_VERIFY_CERTS: bool = True
    REST_TIMEOUT: float = 30.0          # HTTP-Timeout je Request (Upload/GET)
    REST_BATCH: int = 200               # Seitengröße für index_pending
    REST_POLL_START: float = 0.5        # Sync-Job-Poll: Start-Backoff (s)
    REST_POLL_MAX: float = 5.0          # Sync-Job-Poll: max. Backoff (s)
    REST_POLL_DEADLINE: float = 600.0   # max. Wartezeit auf einen Sync-Job (s)

    # Elasticsearch (prod_stack). Server 9.x, Basic-Auth.
    ES_HOST: str = "http://localhost:9200"
    ES_USER: str = "elastic"
    ES_PASSWORD: str = ""
    ES_INDEX: str = "emails"
    # Nur bei https relevant: Zertifikatsprüfung abschaltbar (analog IMAP).
    ES_VERIFY_CERTS: bool = True

    # Anhang-Volltext (Stufe 4): Text aus PDF/DOCX/XLSX/Text extrahieren.
    ATTACHMENT_TEXT: bool = True
    ATTACHMENT_MAX_BYTES: int = 25_000_000  # größere Anhänge überspringen
    ATTACHMENT_MAX_CHARS: int = 100_000  # extrahierten Text je Mail begrenzen

    @property
    def folders(self) -> list[str]:
        return [f.strip() for f in self.IMAP_FOLDERS.split(",") if f.strip()]


settings = Settings()
