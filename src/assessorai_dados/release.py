from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd

from .canonical import slugify
from .models import (
    Proposition,
    ReconciliationRecord,
    ReleaseAsset,
    ReleaseManifest,
    SourcePolicy,
)

PARQUET_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("canonical_key", pa.string()),
        ("country", pa.string()),
        ("jurisdiction_level", pa.string()),
        ("state", pa.string()),
        ("municipality", pa.string()),
        ("house", pa.string()),
        ("type", pa.string()),
        ("number", pa.string()),
        ("year", pa.int32()),
        ("title", pa.string()),
        ("subject", pa.string()),
        ("authors", pa.list_(pa.string())),
        ("presentation_date", pa.date32()),
        ("status", pa.string()),
        ("full_text", pa.string()),
        ("source_url", pa.string()),
        ("text_extraction_method", pa.string()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
        ("content_hash", pa.string()),
        ("provenance_json", pa.string()),
    ]
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat().replace("+00:00", "Z")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def proposition_json(proposition: Proposition) -> dict[str, Any]:
    return proposition.model_dump(mode="json")


def proposition_parquet(proposition: Proposition) -> dict[str, Any]:
    value = proposition.model_dump()
    provenance = value.pop("provenance")
    value["provenance_json"] = json.dumps(
        provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_value
    )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(path: Path, media_type: str, row_count: int | None = None, **metadata) -> ReleaseAsset:
    return ReleaseAsset(
        name=path.name,
        media_type=media_type,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        row_count=row_count,
        **metadata,
    )


def _write_zstd_lines(path: Path, lines: list[bytes]) -> None:
    compressor = zstd.ZstdCompressor(level=19, threads=0, write_checksum=True)
    with path.open("wb") as raw_stream, compressor.stream_writer(raw_stream) as stream:
        for line in lines:
            stream.write(line)
            stream.write(b"\n")


def _chunks(values: list[Any], size: int):
    for start in range(0, len(values), size):
        yield start // size, values[start : start + size]


def _release_datetime(release: str) -> datetime:
    try:
        return datetime.strptime(release, "%Y.%m.%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("release must use YYYY.MM.DD") from exc


def build_release(
    propositions: list[Proposition],
    reconciliation: list[ReconciliationRecord],
    policies: list[SourcePolicy],
    output_dir: Path,
    release: str,
    *,
    max_records_per_asset: int = 50_000,
    embeddings_input: Path | None = None,
) -> ReleaseManifest:
    created_at = _release_datetime(release)
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    assets: list[ReleaseAsset] = []

    grouped: dict[tuple[str, int | None], list[Proposition]] = defaultdict(list)
    for proposition in propositions:
        grouped[(slugify(proposition.house), proposition.year)].append(proposition)

    for (house_slug, year), values in sorted(grouped.items()):
        values.sort(key=lambda item: item.id)
        for part, records in _chunks(values, max_records_per_asset):
            name = f"propositions--{house_slug}--{year or 'unknown'}--part-{part:04d}.parquet"
            path = output_dir / name
            table = pa.Table.from_pylist(
                [proposition_parquet(item) for item in records], schema=PARQUET_SCHEMA
            )
            pq.write_table(
                table,
                path,
                compression="zstd",
                compression_level=19,
                use_dictionary=True,
                write_statistics=True,
                data_page_version="2.0",
            )
            assets.append(
                _asset(
                    path,
                    "application/vnd.apache.parquet",
                    len(records),
                    year=year,
                )
            )

    sorted_propositions = sorted(propositions, key=lambda item: item.id)
    for part, records in _chunks(sorted_propositions, max_records_per_asset):
        path = output_dir / f"propositions--part-{part:04d}.jsonl.zst"
        _write_zstd_lines(
            path,
            [
                json.dumps(
                    proposition_json(item),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                for item in records
            ],
        )
        assets.append(_asset(path, "application/x-ndjson+zstd", len(records)))

        csv_path = output_dir / f"metadata--part-{part:04d}.csv.zst"
        text_buffer = io.StringIO(newline="")
        fieldnames = [
            "id",
            "house",
            "state",
            "municipality",
            "type",
            "number",
            "year",
            "title",
            "subject",
            "authors",
            "presentation_date",
            "status",
            "source_url",
            "content_hash",
        ]
        writer = csv.DictWriter(text_buffer, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for item in records:
            value = proposition_json(item)
            value["authors"] = json.dumps(value["authors"], ensure_ascii=False)
            writer.writerow({key: value.get(key) for key in fieldnames})
        compressor = zstd.ZstdCompressor(level=19, threads=0, write_checksum=True)
        csv_path.write_bytes(compressor.compress(text_buffer.getvalue().encode()))
        assets.append(_asset(csv_path, "text/csv+zstd", len(records)))

    reconciliation_path = output_dir / "reconciliation.jsonl.zst"
    _write_zstd_lines(
        reconciliation_path,
        [
            json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
            for item in reconciliation
        ],
    )
    assets.append(_asset(reconciliation_path, "application/x-ndjson+zstd", len(reconciliation)))

    coverage: dict[str, Any] = {"release": release, "houses": {}, "sources": {}}
    house_counts = Counter((item.house, item.year) for item in propositions)
    for (house, year), count in sorted(house_counts.items()):
        coverage["houses"].setdefault(house, {})[str(year or "unknown")] = count
    source_counts = Counter(
        provenance.source_id for item in propositions for provenance in item.provenance
    )
    coverage["sources"] = dict(sorted(source_counts.items()))
    coverage_path = output_dir / "coverage.json"
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    assets.append(_asset(coverage_path, "application/json"))

    project_root = Path(__file__).resolve().parents[2]
    for source, target_name in [
        (project_root / "schemas" / "proposition.schema.json", "proposition.schema.json"),
        (project_root / "docs" / "data-dictionary.json", "data-dictionary.json"),
        (project_root / "DATA-LICENSE.md", "DATA-LICENSE.md"),
    ]:
        destination = output_dir / target_name
        shutil.copyfile(source, destination)
        assets.append(
            _asset(
                destination,
                "application/json" if destination.suffix == ".json" else "text/markdown",
            )
        )

    if embeddings_input:
        embedding_path = output_dir / embeddings_input.name
        if embedding_path.suffix != ".parquet" or not embedding_path.name.startswith("embeddings-"):
            raise ValueError("embeddings input must be a Parquet named embeddings-{model}.parquet")
        shutil.copyfile(embeddings_input, embedding_path)
        assets.append(_asset(embedding_path, "application/vnd.apache.parquet"))

    actions = Counter(item.action for item in reconciliation)
    used_source_ids = {item.source_id for item in reconciliation}
    policy_by_id = {policy.id: policy for policy in policies}
    source_manifest = []
    for source_id in sorted(used_source_ids):
        policy = policy_by_id.get(source_id)
        if policy:
            source_manifest.append(policy.model_dump(mode="json"))
        else:
            source_manifest.append(
                SourcePolicy(id=source_id, name=source_id.replace("-", " ").title()).model_dump(
                    mode="json"
                )
            )
    publishable = all(
        source["redistribution_status"] in {"allowed", "metadata_only"}
        for source in source_manifest
    )
    manifest = ReleaseManifest(
        release=release,
        created_at=created_at,
        publishable=publishable,
        proposition_count=len(propositions),
        quarantined_count=actions["quarantined"],
        deduplicated_count=actions["deduplicated"],
        assets=sorted(assets, key=lambda item: item.name),
        sources=source_manifest,
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return manifest
