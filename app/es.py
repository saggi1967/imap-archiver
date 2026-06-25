"""Elasticsearch-Client und suchoptimales Index-Mapping."""

from elasticsearch import Elasticsearch

from app.config import settings

# Lowercase-Normalizer für case-insensitive exakte Treffer auf Adressen/Domain.
INDEX_BODY = {
    "settings": {
        "analysis": {
            "normalizer": {
                "lower": {"type": "custom", "filter": ["lowercase"]},
            }
        }
    },
    "mappings": {
        "properties": {
            "mailbox": {"type": "keyword"},
            "uid": {"type": "long"},
            "uidvalidity": {"type": "long"},
            "message_id": {"type": "keyword"},
            # Volltext (deutsch) + exakter Subfeld-Zugriff
            "subject": {
                "type": "text",
                "analyzer": "german",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "body": {"type": "text", "analyzer": "german"},
            "attachment_text": {"type": "text", "analyzer": "german"},
            "from_addr": {"type": "keyword", "normalizer": "lower"},
            "from_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "from_domain": {"type": "keyword", "normalizer": "lower"},
            "to": {"type": "keyword", "normalizer": "lower"},
            "cc": {"type": "keyword", "normalizer": "lower"},
            "date": {"type": "date"},
            "internaldate": {"type": "date"},
            "size": {"type": "long"},
            "has_attachment": {"type": "boolean"},
            "attachment_count": {"type": "integer"},
            "attachments": {
                "type": "nested",
                "properties": {
                    "filename": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "content_type": {"type": "keyword"},
                    "size": {"type": "long"},
                    "has_text": {"type": "boolean"},
                },
            },
        }
    },
}


def client() -> Elasticsearch:
    kwargs: dict = {"basic_auth": (settings.ES_USER, settings.ES_PASSWORD)}
    if settings.ES_HOST.lower().startswith("https"):
        kwargs["verify_certs"] = settings.ES_VERIFY_CERTS
        kwargs["ssl_show_warn"] = settings.ES_VERIFY_CERTS
    return Elasticsearch(settings.ES_HOST, **kwargs)


def ensure_index(es: Elasticsearch, index: str) -> bool:
    """Legt den Index mit Mapping an, falls er fehlt. True = neu erstellt."""
    if es.indices.exists(index=index):
        return False
    es.indices.create(index=index, **INDEX_BODY)
    return True


def sync_mapping(es: Elasticsearch, index: str) -> None:
    """Fügt neue Felder additiv zum bestehenden Mapping hinzu (z. B. attachment_text).

    Elasticsearch akzeptiert das Setzen identischer bestehender + neuer Felder;
    inkompatible Änderungen an vorhandenen Feldern würden hier (gewollt) scheitern.
    """
    es.indices.put_mapping(index=index, properties=INDEX_BODY["mappings"]["properties"])
