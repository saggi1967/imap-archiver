"""Wandelt Roh-RFC822-Bytes in ein suchoptimales Elasticsearch-Dokument."""

from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from app import attachments
from app.config import settings


class _HTMLToText(HTMLParser):
    """Minimaler HTML→Text-Konverter (stdlib, ohne Zusatzabhängigkeit)."""

    _SKIP = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def strip_html(html: str) -> str:
    parser = _HTMLToText()
    try:
        parser.feed(html)
    except Exception:
        return html
    lines = [ln.strip() for ln in parser.text().splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _decode(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _decode_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")


def _domain(addr: str) -> str | None:
    return addr.rsplit("@", 1)[1].lower() if "@" in addr else None


def _addr_list(msg: Message, field: str) -> list[str]:
    raw = msg.get_all(field, [])
    return [a.lower() for _n, a in getaddresses(raw) if a]


def extract_document(row) -> dict:
    """row: sqlite3.Row mit uid, uidvalidity, internaldate, size, raw, mailbox."""
    msg = message_from_bytes(row["raw"])

    text_parts: list[str] = []
    html_parts: list[str] = []
    attachment_meta: list[dict] = []
    attachment_texts: list[str] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        ctype = part.get_content_type()
        if disposition == "attachment" or filename:
            payload = part.get_payload(decode=True) or b""
            decoded_name = _decode(filename)
            entry = {"filename": decoded_name, "content_type": ctype, "size": len(payload)}
            if settings.ATTACHMENT_TEXT:
                text = attachments.extract_text(
                    decoded_name, ctype, payload, settings.ATTACHMENT_MAX_BYTES
                )
                if text:
                    attachment_texts.append(text)
                entry["has_text"] = bool(text)
            attachment_meta.append(entry)
        elif ctype == "text/plain":
            text_parts.append(_decode_text(part))
        elif ctype == "text/html":
            html_parts.append(_decode_text(part))

    body = "\n".join(p for p in text_parts if p).strip()
    if not body and html_parts:
        body = strip_html("\n".join(html_parts))

    attachment_text = "\n\n".join(attachment_texts).strip()
    if len(attachment_text) > settings.ATTACHMENT_MAX_CHARS:
        attachment_text = attachment_text[: settings.ATTACHMENT_MAX_CHARS]

    from_name, from_addr = parseaddr(msg.get("From", ""))
    from_addr = from_addr.lower()

    date_iso = None
    if msg.get("Date"):
        try:
            date_iso = parsedate_to_datetime(msg["Date"]).isoformat()
        except (TypeError, ValueError):
            date_iso = None

    return {
        "mailbox": row["mailbox"],
        "uid": row["uid"],
        "uidvalidity": row["uidvalidity"],
        "message_id": (msg.get("Message-ID") or "").strip() or None,
        "subject": _decode(msg.get("Subject")),
        "from_addr": from_addr or None,
        "from_name": _decode(from_name) or None,
        "from_domain": _domain(from_addr),
        "to": _addr_list(msg, "To"),
        "cc": _addr_list(msg, "Cc"),
        "date": date_iso or row["internaldate"],
        "internaldate": row["internaldate"],
        "size": row["size"],
        "body": body,
        "has_attachment": bool(attachment_meta),
        "attachment_count": len(attachment_meta),
        "attachments": attachment_meta,
        "attachment_text": attachment_text or None,
    }


def doc_id(row) -> str:
    return f"{row['mailbox']}:{row['uidvalidity']}:{row['uid']}"


def iter_attachments(raw: bytes):
    """Liefert (dateiname, content_type, bytes) für jeden Anhang der Roh-Mail."""
    msg = message_from_bytes(raw)
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if disposition == "attachment" or filename:
            payload = part.get_payload(decode=True) or b""
            yield _decode(filename), part.get_content_type(), payload
