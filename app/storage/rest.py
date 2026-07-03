"""REST-Implementierung des StorageBackend — spricht den mailarc-server-Vertrag.

Lese-Operationen sind synchrone GETs. Der schreibintensive Sync-Pfad geht über
``store_email_batch`` als **async Sync-Job** (POST /sync-jobs → 202) plus Poll mit
Backoff (Vorschlag Abschnitt 6): der Upload-Request muss nur das Staging überleben,
die Verarbeitung läuft serverseitig außerhalb jedes HTTP-Timeouts.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Iterator
from datetime import datetime

import httpx

from app.config import settings
from app.storage.base import Row, StatsSummary


class RestStorage:
    def __init__(
        self,
        base_url: str,
        token: str,
        verify: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._verify = verify
        self._timeout = timeout
        self._client: httpx.Client | None = None

    # -- Lebenszyklus -----------------------------------------------------
    def __enter__(self) -> "RestStorage":
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            verify=self._verify,
            timeout=self._timeout,
        )
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None:
        if self._client is not None:
            self._client.close()
            self._client = None
        return None

    def commit(self) -> None:
        # Kein lokaler Transaktionsbegriff — jeder HTTP-Call ist für sich atomar.
        pass

    @property
    def _c(self) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("RestStorage außerhalb des with-Blocks benutzt.")
        return self._client

    # -- Ordner -----------------------------------------------------------
    def get_mailbox(self, name: str) -> Row | None:
        r = self._c.get(f"/mailboxes/{name}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def upsert_mailbox(self, name: str) -> int:
        r = self._c.post("/mailboxes", json={"name": name})
        r.raise_for_status()
        return r.json()["id"]

    def reset_mailbox_state(self, mailbox_id: int, uidvalidity: int) -> None:
        r = self._c.patch(
            f"/mailboxes/{mailbox_id}",
            json={"reset": "state", "uidvalidity": uidvalidity},
        )
        r.raise_for_status()

    def reset_mailbox_full(self, mailbox_id: int) -> None:
        r = self._c.patch(f"/mailboxes/{mailbox_id}", json={"reset": "full"})
        r.raise_for_status()

    def update_mailbox_state(
        self, mailbox_id: int, uidvalidity: int, last_uid: int, imported_at: str
    ) -> None:
        r = self._c.patch(
            f"/mailboxes/{mailbox_id}",
            json={
                "uidvalidity": uidvalidity,
                "last_uid": last_uid,
                "last_import_at": imported_at,
            },
        )
        r.raise_for_status()

    def list_mailboxes_with_counts(self) -> list[Row]:
        r = self._c.get("/mailboxes", params={"with_counts": 1})
        r.raise_for_status()
        return r.json()

    # -- Mails: schreiben (async Sync-Job) --------------------------------
    def store_email_batch(
        self,
        mailbox_id: int,
        mailbox_name: str,
        uidvalidity: int,
        emails: list[dict],
    ) -> tuple[int, int]:
        if not emails:
            return (0, 0)

        # Stabiler Idempotency-Key je Chunk: derselbe Batch (gleicher UID-Bereich)
        # ergibt denselben Key → ein Retry dupliziert den Job nicht.
        key = f"{mailbox_name}:{uidvalidity}:{emails[0]['uid']}-{emails[-1]['uid']}:{len(emails)}"
        payload = {
            "idempotency_key": key,
            "mailbox_name": mailbox_name,
            "uidvalidity": uidvalidity,
            "last_uid": None,  # Wasserzeichen setzt update_mailbox_state separat
            "emails": [self._email_payload(e) for e in emails],
        }
        r = self._c.post("/sync-jobs", json=payload)
        r.raise_for_status()
        tx_id = r.json()["tx_id"]
        job = self._poll_job(tx_id)
        if job["status"] == "failed":
            raise RuntimeError(f"Sync-Job {tx_id} fehlgeschlagen: {job.get('errors')}")
        return job["inserted"], job["skipped"]

    @staticmethod
    def _email_payload(e: dict) -> dict:
        return {
            "uid": e["uid"],
            "uidvalidity": e["uidvalidity"],
            "message_id": e.get("message_id"),
            "from_addr": e.get("from_addr"),
            "to_addr": e.get("to_addr"),
            "subject": e.get("subject"),
            "date_header": e.get("date_header"),
            "internaldate": e.get("internaldate"),
            "size": e.get("size"),
            "raw_base64": base64.b64encode(e["raw"]).decode("ascii"),
        }

    def _poll_job(self, tx_id: str) -> dict:
        delay = settings.REST_POLL_START
        deadline = time.monotonic() + settings.REST_POLL_DEADLINE
        while True:
            r = self._c.get(f"/sync-jobs/{tx_id}")
            r.raise_for_status()
            job = r.json()
            if job["status"] in ("done", "failed"):
                return job
            if time.monotonic() > deadline:
                raise TimeoutError(f"Sync-Job {tx_id} nicht rechtzeitig fertig")
            time.sleep(delay)
            delay = min(delay * 2, settings.REST_POLL_MAX)

    # -- Mails: Index / lesen --------------------------------------------
    def count_pending_index(self, reindex: bool) -> int:
        r = self._c.get("/emails/count", params={"reindex": reindex})
        r.raise_for_status()
        return r.json()["count"]

    def iter_emails_for_index(self, reindex: bool) -> Iterator[Row]:
        cursor = 0
        while True:
            r = self._c.get(
                "/emails",
                params={
                    "index_pending": 1,
                    "reindex": reindex,
                    "cursor": cursor,
                    "limit": settings.REST_BATCH,
                },
            )
            r.raise_for_status()
            page = r.json()
            for item in page["items"]:
                yield {
                    "id": item["id"],
                    "mailbox": item["mailbox"],
                    "uid": item["uid"],
                    "uidvalidity": item["uidvalidity"],
                    "internaldate": item["internaldate"],
                    "size": item["size"],
                    "raw": base64.b64decode(item["raw_base64"]),
                }
            if page["next_cursor"] is None:
                break
            cursor = page["next_cursor"]

    def mark_indexed(self, email_ids: list[int], indexed_at: str) -> None:
        if not email_ids:
            return
        r = self._c.patch(
            "/emails/mark-indexed",
            json={"ids": email_ids, "indexed_at": indexed_at},
        )
        r.raise_for_status()

    def get_raw_by_ref(self, mailbox: str, uidvalidity: int, uid: int) -> Row | None:
        r = self._c.get(f"/emails/{mailbox}/{uidvalidity}/{uid}/raw")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return {"raw": r.content}

    def get_raw_by_message_id(self, message_id: str) -> Row | None:
        r = self._c.get(f"/emails/by-message-id/{message_id}/raw")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return {"raw": r.content}

    def stats_summary(self, top: int) -> StatsSummary:
        r = self._c.get("/stats/summary", params={"top": top})
        r.raise_for_status()
        s = r.json()

        def _dt(v: str | None) -> datetime | None:
            return datetime.fromisoformat(v).replace(tzinfo=None) if v else None

        return StatsSummary(
            total=s["total"],
            total_size=s["total_size"],
            span_start=_dt(s["span_start"]),
            span_end=_dt(s["span_end"]),
            distinct_senders=s["distinct_senders"],
            # JSON-Objekt-Schlüssel sind Strings → zurück nach int.
            per_year={int(k): v for k, v in s["per_year"].items()},
            per_month={int(k): v for k, v in s["per_month"].items()},
            per_weekday={int(k): v for k, v in s["per_weekday"].items()},
            top_senders=[(name, cnt) for name, cnt in s["top_senders"]],
        )
