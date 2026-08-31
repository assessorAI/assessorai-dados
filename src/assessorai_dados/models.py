from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RedistributionStatus = Literal["allowed", "metadata_only", "pending", "blocked"]


class SourcePolicy(BaseModel):
    id: str
    name: str
    path_patterns: list[str] = Field(default_factory=list)
    house: str | None = None
    jurisdiction_level: Literal["federal", "state", "municipal", "unknown"] = "unknown"
    state: str | None = None
    municipality: str | None = None
    terms_url: str | None = None
    source_license: str | None = None
    redistribution_status: RedistributionStatus = "pending"
    attribution: str | None = None


class Provenance(BaseModel):
    source_id: str
    source_record_id: str | None = None
    source_url: str | None = None
    source_file: str
    scraped_at: datetime | None = None
    extraction_method: str | None = None
    content_hash: str
    redistribution_status: RedistributionStatus


class Proposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    canonical_key: str
    country: str = "BR"
    jurisdiction_level: Literal["federal", "state", "municipal", "unknown"] = "unknown"
    state: str | None = None
    municipality: str | None = None
    house: str
    type: str | None = None
    number: str | None = None
    year: int | None = None
    title: str
    subject: str | None = None
    authors: list[str] = Field(default_factory=list)
    presentation_date: date | None = None
    status: str | None = None
    full_text: str | None = None
    source_url: str | None = None
    text_extraction_method: str | None = None
    collected_at: datetime | None = None
    content_hash: str
    provenance: list[Provenance] = Field(default_factory=list)


class ReconciliationRecord(BaseModel):
    source_file: str
    source_index: int
    source_id: str
    source_fingerprint: str
    action: Literal["published", "deduplicated", "quarantined"]
    proposition_id: str | None = None
    reason: str | None = None


class ReleaseAsset(BaseModel):
    name: str
    media_type: str
    sha256: str
    size: int
    row_count: int | None = None
    source_id: str | None = None
    year: int | None = None


class ReleaseManifest(BaseModel):
    schema_version: str = "1.0.0"
    release: str
    created_at: datetime
    publishable: bool
    proposition_count: int
    quarantined_count: int
    deduplicated_count: int
    assets: list[ReleaseAsset]
    sources: list[dict[str, Any]]


class SearchFilters(BaseModel):
    query: str | None = None
    house: str | None = None
    state: str | None = None
    municipality: str | None = None
    proposition_type: str | None = None
    year: int | None = None
    author: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class SearchResult(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None
    release: str | None = None
