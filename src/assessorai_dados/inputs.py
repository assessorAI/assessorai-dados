from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def discover_json_files(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".jl"}:
            files.add(path.resolve())
        elif path.is_dir():
            for pattern in ("*.json", "*.jsonl", "*.jl"):
                files.update(item.resolve() for item in path.rglob(pattern))
    return sorted(files)


def read_records(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.lower() in {".jsonl", ".jl"}:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number}: record must be an object")
                yield value
        return

    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        value = value["items"]
    if not isinstance(value, list):
        raise ValueError(f"{path}: JSON must be an array or an object with an items array")
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{index}: record must be an object")
        yield record


def iter_input_records(paths: list[Path]):
    for path in discover_json_files(paths):
        for index, record in enumerate(read_records(path)):
            yield path, index, record
