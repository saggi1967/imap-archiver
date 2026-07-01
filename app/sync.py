"""Sync-Logik: Initial-Voll-Import bzw. Inkrement seit letztem Import."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from imapclient import IMAPClient

from app import imap
from app.storage.base import StorageBackend

# IMAP-FETCH-Items: Rohnachricht, Servergröße und interne Zustellzeit.
FETCH_ITEMS = [b"RFC822", b"RFC822.SIZE", b"INTERNALDATE"]
BATCH = 200


@dataclass
class FolderResult:
    folder: str
    mode: str  # "initial" | "inkrement" | "resync"
    fetched: int
    inserted: int
    skipped: int
    last_uid: int


def _decode(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _parse_headers(raw: bytes) -> dict:
    msg = message_from_bytes(raw)
    date_header = None
    if msg["Date"]:
        try:
            date_header = parsedate_to_datetime(msg["Date"]).isoformat()
        except (TypeError, ValueError):
            date_header = msg["Date"]
    return {
        "message_id": (msg["Message-ID"] or "").strip() or None,
        "from_addr": _decode(msg["From"]),
        "to_addr": _decode(msg["To"]),
        "subject": _decode(msg["Subject"]),
        "date_header": date_header,
    }


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def sync_folder(
    storage: StorageBackend,
    client: IMAPClient,
    folder: str,
    on_start: Callable[[str, str, int], None] | None = None,
    on_tick: Callable[[int], None] | None = None,
) -> FolderResult:
    mailbox_id = storage.upsert_mailbox(folder)
    stored = storage.get_mailbox(folder)
    uidvalidity = imap.examine(client, folder)

    # UIDVALIDITY-Wechsel => bisherige UIDs ungültig => Voll-Resync.
    if stored["uidvalidity"] is not None and stored["uidvalidity"] != uidvalidity:
        storage.reset_mailbox_state(mailbox_id, uidvalidity)
        last_uid = 0
        mode = "resync"
    else:
        last_uid = stored["last_uid"] or 0
        mode = "initial" if last_uid == 0 else "inkrement"

    uids = imap.search_new_uids(client, last_uid)

    if on_start:
        on_start(folder, mode, len(uids))

    inserted = skipped = 0
    max_uid = last_uid
    for chunk in _chunks(uids, BATCH):
        response = client.fetch(chunk, FETCH_ITEMS)
        for uid in chunk:
            data = response.get(uid)
            if not data:
                if on_tick:
                    on_tick(1)
                continue
            raw = data[b"RFC822"]
            now = datetime.now(timezone.utc).isoformat()
            internaldate = data[b"INTERNALDATE"]
            ok = storage.insert_email(
                mailbox_id=mailbox_id,
                uid=uid,
                uidvalidity=uidvalidity,
                size=data[b"RFC822.SIZE"],
                internaldate=internaldate.isoformat() if internaldate else None,
                raw=raw,
                imported_at=now,
                **_parse_headers(raw),
            )
            inserted += ok
            skipped += not ok
            max_uid = max(max_uid, uid)
            if on_tick:
                on_tick(1)

    storage.update_mailbox_state(
        mailbox_id, uidvalidity, max_uid, datetime.now(timezone.utc).isoformat()
    )
    return FolderResult(folder, mode, len(uids), inserted, skipped, max_uid)


def sync_folders(
    storage: StorageBackend,
    folders: list[str],
    on_start: Callable[[str, str, int], None] | None = None,
    on_tick: Callable[[int], None] | None = None,
) -> list[FolderResult]:
    results: list[FolderResult] = []
    with imap.imap_session() as client:
        for folder in folders:
            results.append(sync_folder(storage, client, folder, on_start, on_tick))
            storage.commit()
    return results
