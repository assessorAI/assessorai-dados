from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dateutil import parser as date_parser

from .models import Proposition, Provenance, ReconciliationRecord, SourcePolicy

NAMESPACE = uuid.UUID("420a7db3-1567-5edb-9dd4-fc6d784a95d3")
SPACE_RE = re.compile(r"\s+")
NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_space(value: Any) -> str | None:
    if value is None:
        return None
    text = SPACE_RE.sub(" ", str(value)).strip()
    return text or None


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return NON_SLUG_RE.sub("-", ascii_value.lower()).strip("-")


def normalize_url(value: Any) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        return text
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        match = re.search(r"\b(19|20)\d{2}\b", str(value))
        return int(match.group()) if match else None


def parse_date(value: Any) -> date | None:
    text = normalize_space(value)
    if not text:
        return None
    try:
        return date_parser.parse(text, dayfirst=True).date()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    text = normalize_space(value)
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_authors(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else re.split(r"[;,]", str(value))
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        author = normalize_space(raw)
        if author and author.casefold() not in seen:
            result.append(author)
            seen.add(author.casefold())
    return result


def stable_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode()


def sha256_value(value: Any) -> str:
    return hashlib.sha256(stable_json(value)).hexdigest()


def load_source_policies(path: Path) -> list[SourcePolicy]:
    return [
        SourcePolicy.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def resolve_policy(
    path: Path, record: dict[str, Any], policies: list[SourcePolicy]
) -> SourcePolicy:
    path_key = str(path).lower()
    house = normalize_space(record.get("house") or record.get("Casa") or record.get("origem"))
    for policy in policies:
        if any(pattern.lower() in path_key for pattern in policy.path_patterns):
            return policy
        if house and policy.house and slugify(house) == slugify(policy.house):
            return policy
    source_id = f"unregistered-{slugify(house or path.stem)}"
    return SourcePolicy(id=source_id, name=house or path.stem, house=house)


def _record_value(record: dict[str, Any], *keys: str) -> Any:
    metadata = record.get("metadata") or record.get("meta") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    for key in keys:
        if record.get(key) not in (None, ""):
            return record[key]
        if isinstance(metadata, dict) and metadata.get(key) not in (None, ""):
            return metadata[key]
    return None


def canonicalize_record(
    record: dict[str, Any], source_file: Path, policy: SourcePolicy
) -> Proposition:
    house = normalize_space(_record_value(record, "house", "Casa", "casa")) or policy.house
    title = normalize_space(_record_value(record, "title", "Titulo", "titulo"))
    if not house or not title:
        raise ValueError("minimum_fields_missing: house and title are required")

    proposition_type = normalize_space(_record_value(record, "type", "tipo", "Tipo"))
    number_raw = _record_value(record, "number", "numero", "Numero")
    number = normalize_space(number_raw)
    year = parse_int(_record_value(record, "year", "ano", "Ano"))
    source_url = normalize_url(_record_value(record, "url", "source_url", "Url"))
    source_record_id = normalize_space(_record_value(record, "id", "uuid", "source_id"))
    subject = normalize_space(_record_value(record, "subject", "ementa", "Ementa"))
    full_text = normalize_space(
        _record_value(record, "full_text", "content", "texto", "inteiro_teor")
    )
    if policy.redistribution_status == "metadata_only":
        full_text = None
    status = normalize_space(_record_value(record, "status", "situacao", "Status"))
    authors = normalize_authors(_record_value(record, "author", "autor", "Autoria"))
    presentation_date = parse_date(
        _record_value(record, "presentation_date", "data_apresentacao", "DataApresentacao")
    )
    scraped_at = parse_datetime(_record_value(record, "scraped_at", "coletado_em"))

    if proposition_type and number and year:
        canonical_key = ":".join(
            [slugify(house), slugify(proposition_type), slugify(number), str(year)]
        )
    elif source_record_id:
        canonical_key = f"{policy.id}:source:{slugify(source_record_id)}"
    elif source_url:
        canonical_key = f"{policy.id}:url:{source_url}"
    else:
        canonical_key = f"{policy.id}:fallback:{sha256_value([title, subject])}"

    proposition_id = str(uuid.uuid5(NAMESPACE, canonical_key))
    raw_content_hash = sha256_value(record)
    text_method = normalize_space(_record_value(record, "extraction_method"))
    if not text_method and full_text:
        text_method = "source_or_ocr"
    if policy.redistribution_status == "metadata_only":
        text_method = None
    provenance = Provenance(
        source_id=policy.id,
        source_record_id=source_record_id,
        source_url=source_url,
        source_file=str(source_file),
        scraped_at=scraped_at,
        extraction_method=text_method,
        content_hash=raw_content_hash,
        redistribution_status=policy.redistribution_status,
    )
    content_hash = sha256_value(
        [canonical_key, title, subject, full_text, authors, status, presentation_date]
    )
    return Proposition(
        id=proposition_id,
        canonical_key=canonical_key,
        jurisdiction_level=policy.jurisdiction_level,
        state=policy.state,
        municipality=policy.municipality,
        house=house,
        type=proposition_type,
        number=number,
        year=year,
        title=title,
        subject=subject,
        authors=authors,
        presentation_date=presentation_date,
        status=status,
        full_text=full_text,
        source_url=source_url,
        text_extraction_method=text_method,
        collected_at=scraped_at,
        content_hash=content_hash,
        provenance=[provenance],
    )


def _prefer_longer(left: str | None, right: str | None) -> str | None:
    return right if len(right or "") > len(left or "") else left


def merge_propositions(existing: Proposition, incoming: Proposition) -> Proposition:
    data = existing.model_dump()
    data["title"] = _prefer_longer(existing.title, incoming.title)
    data["subject"] = _prefer_longer(existing.subject, incoming.subject)
    data["full_text"] = _prefer_longer(existing.full_text, incoming.full_text)
    data["status"] = incoming.status or existing.status
    data["source_url"] = existing.source_url or incoming.source_url
    data["presentation_date"] = existing.presentation_date or incoming.presentation_date
    data["collected_at"] = max(
        [value for value in [existing.collected_at, incoming.collected_at] if value],
        default=None,
    )
    authors: list[str] = []
    seen: set[str] = set()
    for author in [*existing.authors, *incoming.authors]:
        if author.casefold() not in seen:
            authors.append(author)
            seen.add(author.casefold())
    data["authors"] = authors
    provenance_by_hash = {
        item.content_hash: item for item in [*existing.provenance, *incoming.provenance]
    }
    data["provenance"] = list(provenance_by_hash.values())
    data["content_hash"] = sha256_value(
        [data["canonical_key"], data["title"], data["subject"], data["full_text"], authors]
    )
    return Proposition.model_validate(data)


def reconcile_records(
    entries: Iterable[tuple[Path, int, dict[str, Any]]],
    policies: list[SourcePolicy],
    *,
    allow_pending: bool = False,
) -> tuple[list[Proposition], list[ReconciliationRecord]]:
    propositions: dict[str, Proposition] = {}
    reconciliation: list[ReconciliationRecord] = []
    for source_file, index, record in entries:
        policy = resolve_policy(source_file, record, policies)
        fingerprint = sha256_value(record)
        if policy.redistribution_status in {"pending", "blocked"} and not allow_pending:
            reconciliation.append(
                ReconciliationRecord(
                    source_file=str(source_file),
                    source_index=index,
                    source_id=policy.id,
                    source_fingerprint=fingerprint,
                    action="quarantined",
                    reason=f"redistribution_{policy.redistribution_status}",
                )
            )
            continue
        try:
            proposition = canonicalize_record(record, source_file, policy)
        except ValueError as exc:
            reconciliation.append(
                ReconciliationRecord(
                    source_file=str(source_file),
                    source_index=index,
                    source_id=policy.id,
                    source_fingerprint=fingerprint,
                    action="quarantined",
                    reason=str(exc),
                )
            )
            continue
        existing = propositions.get(proposition.id)
        action = "deduplicated" if existing else "published"
        propositions[proposition.id] = (
            merge_propositions(existing, proposition) if existing else proposition
        )
        reconciliation.append(
            ReconciliationRecord(
                source_file=str(source_file),
                source_index=index,
                source_id=policy.id,
                source_fingerprint=fingerprint,
                action=action,
                proposition_id=proposition.id,
            )
        )
    return sorted(propositions.values(), key=lambda item: item.id), reconciliation
