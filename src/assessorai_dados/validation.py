from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import zstandard as zstd

from .models import ReleaseManifest
from .release import sha256_file


def validate_release(
    release_dir: Path,
    *,
    max_asset_size: int = 2 * 1024**3,
    require_publishable: bool = False,
) -> dict[str, int]:
    manifest_path = release_dir / "manifest.json"
    manifest = ReleaseManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if require_publishable and not manifest.publishable:
        raise ValueError("release contains sources without redistribution clearance")
    parquet_rows = 0
    checked = 0
    for asset in manifest.assets:
        path = release_dir / asset.name
        if not path.is_file():
            raise ValueError(f"missing asset: {asset.name}")
        if path.stat().st_size >= max_asset_size:
            raise ValueError(f"asset exceeds size limit: {asset.name}")
        if sha256_file(path) != asset.sha256:
            raise ValueError(f"checksum mismatch: {asset.name}")
        if asset.name.startswith("propositions--") and asset.name.endswith(".parquet"):
            rows = pq.read_metadata(path).num_rows
            if asset.row_count != rows:
                raise ValueError(f"row count mismatch: {asset.name}")
            parquet_rows += rows
        if asset.name.endswith(".jsonl.zst"):
            with path.open("rb") as raw_stream:
                reader = zstd.ZstdDecompressor().stream_reader(raw_stream)
                for line in reader.read().splitlines():
                    json.loads(line)
        checked += 1
    if parquet_rows != manifest.proposition_count:
        raise ValueError(
            f"manifest proposition count {manifest.proposition_count} "
            f"!= parquet rows {parquet_rows}"
        )
    return {"assets": checked, "propositions": parquet_rows}
