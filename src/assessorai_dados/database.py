from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from openai import OpenAI
from sqlalchemy import Engine, create_engine, text

from .models import ReleaseManifest, SearchFilters, SearchResult
from .settings import Settings, get_settings


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded))
        return max(0, int(value["offset"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


class LegislativeRepository:
    def __init__(self, engine: Engine, settings: Settings | None = None):
        self.engine = engine
        self.settings = settings or get_settings()

    def _query_embedding(self, query: str) -> list[float] | None:
        if not self.settings.openai_api_key:
            return None
        response = OpenAI(api_key=self.settings.openai_api_key).embeddings.create(
            model=self.settings.openai_embedding_model,
            input=[query],
        )
        return list(response.data[0].embedding)

    @staticmethod
    def _filters(filters: SearchFilters, params: dict[str, Any]) -> list[str]:
        clauses: list[str] = []
        mapping = {
            "house": filters.house,
            "state": filters.state,
            "municipality": filters.municipality,
            "type": filters.proposition_type,
            "year": filters.year,
        }
        for column, value in mapping.items():
            if value is not None:
                clauses.append(f"p.{column} = :{column}")
                params[column] = value
        if filters.author:
            clauses.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(p.authors) a "
                "WHERE a ILIKE :author)"
            )
            params["author"] = f"%{filters.author}%"
        return clauses

    def search(self, filters: SearchFilters) -> SearchResult:
        offset = decode_cursor(filters.cursor)
        params: dict[str, Any] = {"limit": filters.limit + 1, "offset": offset}
        clauses = self._filters(filters, params)
        query = (filters.query or "").strip()
        embedding = self._query_embedding(query) if query else None
        if query:
            params["query"] = query
            params["identifier"] = query.replace(" ", "")
            clauses.append(
                "(p.search_document @@ websearch_to_tsquery('portuguese', :query) "
                "OR replace(coalesce(p.type, '') || coalesce(p.number, '') || "
                "coalesce(p.year::text, ''), ' ', '') "
                "ILIKE '%' || :identifier || '%')"
            )
        where = " AND ".join(clauses) if clauses else "TRUE"
        if embedding:
            params["embedding"] = "[" + ",".join(str(value) for value in embedding) + "]"
            score_sql = (
                "(CASE WHEN replace(coalesce(p.type, '') || coalesce(p.number, '') || "
                "coalesce(p.year::text, ''), ' ', '') ILIKE '%' || :identifier || '%' "
                "THEN 10 ELSE 0 END) + "
                "ts_rank_cd(p.search_document, websearch_to_tsquery('portuguese', :query)) + "
                "CASE WHEN p.embedding IS NULL THEN 0 "
                "ELSE 1 - (p.embedding <=> CAST(:embedding AS vector)) END"
            )
        elif query:
            score_sql = (
                "(CASE WHEN replace(coalesce(p.type, '') || coalesce(p.number, '') || "
                "coalesce(p.year::text, ''), ' ', '') ILIKE '%' || :identifier || '%' "
                "THEN 10 ELSE 0 END) + "
                "ts_rank_cd(p.search_document, websearch_to_tsquery('portuguese', :query))"
            )
        else:
            score_sql = "0"
        sql = text(
            f"""
            SELECT p.id::text, p.house, p.state, p.municipality, p.type, p.number, p.year,
                   p.title, p.subject, p.authors, p.presentation_date, p.status,
                   p.source_url, p.content_hash, p.dataset_release,
                   {score_sql} AS score,
                   CASE WHEN p.full_text IS NULL THEN NULL
                        ELSE left(p.full_text, 600) END AS excerpt
            FROM propositions p
            WHERE {where}
            ORDER BY score DESC, p.presentation_date DESC NULLS LAST, p.id
            LIMIT :limit OFFSET :offset
            """
        )
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, params).mappings()]
        has_more = len(rows) > filters.limit
        items = rows[: filters.limit]
        for item in items:
            if item.get("presentation_date"):
                item["presentation_date"] = item["presentation_date"].isoformat()
            item["score"] = float(item.get("score") or 0)
        next_cursor = encode_cursor(offset + filters.limit) if has_more else None
        release = items[0].get("dataset_release") if items else self.current_release()
        return SearchResult(items=items, next_cursor=next_cursor, release=release)

    def get_proposition(self, proposition_id: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id::text, canonical_key, country, jurisdiction_level, state, municipality,
                   house, type, number, year, title, subject, authors, presentation_date,
                   status, source_url, text_extraction_method, collected_at, content_hash,
                   provenance, dataset_release, length(coalesce(full_text, '')) AS text_length
            FROM propositions WHERE id::text = :id
            """
        )
        with self.engine.connect() as connection:
            row = connection.execute(sql, {"id": proposition_id}).mappings().first()
        if not row:
            return None
        value = dict(row)
        for key in ("presentation_date", "collected_at"):
            if value.get(key):
                value[key] = value[key].isoformat()
        return value

    def read_text(
        self, proposition_id: str, offset: int = 0, max_chars: int = 20_000
    ) -> dict[str, Any] | None:
        max_chars = max(1, min(max_chars, 20_000))
        offset = max(0, offset)
        sql = text(
            """
            SELECT title, substring(full_text FROM :start FOR :length) AS text,
                   length(coalesce(full_text, '')) AS total_length
            FROM propositions WHERE id::text = :id
            """
        )
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sql, {"id": proposition_id, "start": offset + 1, "length": max_chars}
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        total = int(row["total_length"] or 0)
        next_offset = offset + len(row["text"] or "")
        return {
            "id": proposition_id,
            "title": row["title"],
            "text": row["text"] or "",
            "offset": offset,
            "next_offset": next_offset if next_offset < total else None,
            "total_length": total,
        }

    def related(self, proposition_id: str, limit: int = 10) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT candidate.id::text, candidate.title, candidate.house, candidate.type,
                   candidate.number, candidate.year, candidate.subject, candidate.source_url,
                   CASE
                     WHEN source.embedding IS NOT NULL AND candidate.embedding IS NOT NULL
                     THEN 1 - (candidate.embedding <=> source.embedding)
                     ELSE ts_rank_cd(
                         candidate.search_document,
                         plainto_tsquery('portuguese', source.subject)
                     )
                   END AS score
            FROM propositions source
            JOIN propositions candidate ON candidate.id <> source.id
            WHERE source.id::text = :id
              AND (source.embedding IS NOT NULL OR source.subject IS NOT NULL)
            ORDER BY score DESC NULLS LAST, candidate.id
            LIMIT :limit
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                sql, {"id": proposition_id, "limit": min(max(limit, 1), 50)}
            ).mappings()
            return [{**dict(row), "score": float(row["score"] or 0)} for row in rows]

    def list_sources(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM dataset_sources ORDER BY name")
            ).mappings()
            return [dict(row) for row in rows]

    def list_releases(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT version, created_at, proposition_count, github_repository, is_current "
                    "FROM dataset_releases ORDER BY created_at DESC"
                )
            ).mappings()
            return [dict(row) for row in rows]

    def get_release(self, version: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT version, created_at, proposition_count, manifest, "
                        "github_repository, "
                        "is_current FROM dataset_releases WHERE version = :version "
                        "OR (:version = 'latest' AND is_current = TRUE) "
                        "ORDER BY is_current DESC LIMIT 1"
                    ),
                    {"version": version},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def current_release(self) -> str | None:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT version FROM dataset_releases WHERE is_current LIMIT 1")
            ).scalar_one_or_none()


def create_repository(settings: Settings | None = None) -> LegislativeRepository:
    settings = settings or get_settings()
    return LegislativeRepository(
        create_engine(normalize_database_url(settings.database_url), pool_pre_ping=True),
        settings,
    )


def apply_migrations(engine: Engine, migrations_dir: Path) -> None:
    with engine.begin() as connection:
        for path in sorted(migrations_dir.glob("*.sql")):
            connection.exec_driver_sql(path.read_text(encoding="utf-8"))


def _iter_parquet_records(release_dir: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(release_dir.glob("propositions--*--part-*.parquet")):
        for row in pq.read_table(path).to_pylist():
            row["provenance"] = json.loads(row.pop("provenance_json"))
            yield row


def load_release(
    engine: Engine,
    release_dir: Path,
    github_repository: str,
    *,
    allow_preview: bool = False,
) -> int:
    manifest = ReleaseManifest.model_validate_json(
        (release_dir / "manifest.json").read_text(encoding="utf-8")
    )
    if not manifest.publishable and not allow_preview:
        raise ValueError("preview release requires allow_preview=True")
    records = list(_iter_parquet_records(release_dir))
    if len(records) != manifest.proposition_count:
        raise ValueError("Parquet row count does not match manifest")
    with engine.begin() as connection:
        connection.execute(text("UPDATE dataset_releases SET is_current = FALSE"))
        for source in manifest.sources:
            connection.execute(
                text(
                    """
                    INSERT INTO dataset_sources
                        (id, name, house, jurisdiction_level, state, municipality, terms_url,
                         source_license, redistribution_status, attribution)
                    VALUES
                        (:id, :name, :house, :jurisdiction_level, :state, :municipality, :terms_url,
                         :source_license, :redistribution_status, :attribution)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name, house = EXCLUDED.house,
                        jurisdiction_level = EXCLUDED.jurisdiction_level, state = EXCLUDED.state,
                        municipality = EXCLUDED.municipality, terms_url = EXCLUDED.terms_url,
                        source_license = EXCLUDED.source_license,
                        redistribution_status = EXCLUDED.redistribution_status,
                        attribution = EXCLUDED.attribution, updated_at = now()
                    """
                ),
                source,
            )
        for row in records:
            params = {**row, "dataset_release": manifest.release}
            params["authors"] = json.dumps(params["authors"], ensure_ascii=False)
            params["provenance_json"] = json.dumps(params.pop("provenance"), ensure_ascii=False)
            connection.execute(
                text(
                    """
                    INSERT INTO propositions
                        (id, canonical_key, country, jurisdiction_level, state, municipality,
                         house, type, number, year, title, subject, authors, presentation_date,
                         status, full_text, source_url, text_extraction_method, collected_at,
                         content_hash, provenance, dataset_release)
                    VALUES
                        (CAST(:id AS uuid), :canonical_key, :country, :jurisdiction_level, :state,
                         :municipality, :house, :type, :number, :year, :title, :subject,
                         CAST(:authors AS jsonb), :presentation_date, :status, :full_text,
                         :source_url, :text_extraction_method, :collected_at, :content_hash,
                         CAST(:provenance_json AS jsonb), :dataset_release)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title, subject = EXCLUDED.subject,
                        authors = EXCLUDED.authors, status = EXCLUDED.status,
                        full_text = EXCLUDED.full_text, source_url = EXCLUDED.source_url,
                        collected_at = EXCLUDED.collected_at, content_hash = EXCLUDED.content_hash,
                        provenance = EXCLUDED.provenance, dataset_release = EXCLUDED.dataset_release
                    """
                ),
                params,
            )
            connection.execute(
                text("DELETE FROM proposition_sources WHERE proposition_id = CAST(:id AS uuid)"),
                {"id": row["id"]},
            )
            for provenance in json.loads(params["provenance_json"]):
                connection.execute(
                    text(
                        """
                        INSERT INTO proposition_sources
                            (proposition_id, source_id, source_record_id, source_url, source_file,
                             scraped_at, extraction_method, content_hash, redistribution_status)
                        VALUES
                            (CAST(:proposition_id AS uuid), :source_id,
                             :source_record_id, :source_url,
                             :source_file, :scraped_at, :extraction_method, :content_hash,
                             :redistribution_status)
                        """
                    ),
                    {"proposition_id": row["id"], **provenance},
                )
            connection.execute(
                text("DELETE FROM proposition_texts WHERE proposition_id = CAST(:id AS uuid)"),
                {"id": row["id"]},
            )
            full_text = row.get("full_text") or ""
            for chunk_number, start in enumerate(range(0, len(full_text), 20_000)):
                chunk_text = full_text[start : start + 20_000]
                connection.execute(
                    text(
                        """
                        INSERT INTO proposition_texts
                            (proposition_id, content_hash, chunk_number, chunk_text,
                             start_offset, end_offset)
                        VALUES
                            (CAST(:id AS uuid), :content_hash, :chunk_number, :chunk_text,
                             :start_offset, :end_offset)
                        """
                    ),
                    {
                        "id": row["id"],
                        "content_hash": row["content_hash"],
                        "chunk_number": chunk_number,
                        "chunk_text": chunk_text,
                        "start_offset": start,
                        "end_offset": start + len(chunk_text),
                    },
                )

        for embeddings_path in sorted(release_dir.glob("embeddings-*.parquet")):
            for embedding_row in pq.read_table(embeddings_path).to_pylist():
                embedding = embedding_row.get("embedding")
                if not embedding or len(embedding) != 1536:
                    raise ValueError(f"invalid embedding in {embeddings_path.name}")
                vector = "[" + ",".join(str(value) for value in embedding) + "]"
                connection.execute(
                    text(
                        "UPDATE propositions SET embedding = CAST(:embedding AS vector) "
                        "WHERE id::text = :id"
                    ),
                    {"id": str(embedding_row["id"]), "embedding": vector},
                )
        connection.execute(
            text(
                """
                INSERT INTO dataset_releases
                    (version, created_at, proposition_count, manifest,
                     github_repository, is_current)
                VALUES (:version, :created_at, :count, CAST(:manifest AS jsonb), :repository, TRUE)
                ON CONFLICT (version) DO UPDATE SET
                    proposition_count = EXCLUDED.proposition_count,
                    manifest = EXCLUDED.manifest, github_repository = EXCLUDED.github_repository,
                    is_current = TRUE, loaded_at = now()
                """
            ),
            {
                "version": manifest.release,
                "created_at": manifest.created_at,
                "count": manifest.proposition_count,
                "manifest": manifest.model_dump_json(),
                "repository": github_repository,
            },
        )
    return len(records)
