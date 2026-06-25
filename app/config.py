from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # IMAP-Verbindung zum Firmenserver
    IMAP_HOST: str = "localhost"
    IMAP_PORT: int = 993
    IMAP_SSL: bool = True
    # Zertifikatsprüfung. Auf false setzen, wenn das Server-Zertifikat einen
    # bekannten Hostname-Mismatch hat und das bewusst ignoriert werden soll.
    IMAP_SSL_VERIFY: bool = True
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""

    # Komma-getrennte Liste der zu importierenden Ordner. Default: nur Posteingang.
    IMAP_FOLDERS: str = "INBOX"

    # Pfad zur lokalen SQLite-Datei
    DB_PATH: str = "mailarc.db"

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
