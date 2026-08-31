from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sqlalchemy import create_engine

from .canonical import load_source_policies, reconcile_records
from .database import apply_migrations, load_release
from .inputs import iter_input_records
from .release import build_release
from .settings import get_settings
from .validation import validate_release


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build(args: argparse.Namespace) -> None:
    policies = load_source_policies(args.sources)
    propositions, reconciliation = reconcile_records(
        iter_input_records(args.inputs), policies, allow_pending=args.allow_pending
    )
    manifest = build_release(
        propositions,
        reconciliation,
        policies,
        args.output,
        args.release,
        max_records_per_asset=args.max_records_per_asset,
        embeddings_input=args.embeddings,
    )
    print(manifest.model_dump_json(indent=2))


def _validate(args: argparse.Namespace) -> None:
    print(
        json.dumps(
            validate_release(args.release_dir, require_publishable=args.require_publishable),
            indent=2,
        )
    )


def _migrate(args: argparse.Namespace) -> None:
    engine = create_engine(args.database_url)
    apply_migrations(engine, args.migrations)
    print("migrations applied")


def _load(args: argparse.Namespace) -> None:
    engine = create_engine(args.database_url)
    count = load_release(
        engine,
        args.release_dir,
        args.github_repository,
        allow_preview=args.allow_preview,
    )
    print(json.dumps({"loaded": count}))


def _upload_draft(args: argparse.Namespace) -> None:
    validate_release(args.release_dir)
    manifest = json.loads((args.release_dir / "manifest.json").read_text(encoding="utf-8"))
    release = manifest["release"]
    assets = [str(path) for path in sorted(args.release_dir.iterdir()) if path.is_file()]
    existing = subprocess.run(
        ["gh", "release", "view", release, "--repo", args.repository],
        check=False,
        capture_output=True,
    )
    if existing.returncode != 0:
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                release,
                "--repo",
                args.repository,
                "--draft",
                "--title",
                f"Dataset {release}",
                "--notes",
                (
                    "Release validado do corpus legislativo: "
                    f"{manifest['proposition_count']} proposições."
                ),
            ],
            check=True,
        )
    subprocess.run(
        ["gh", "release", "upload", release, "--repo", args.repository, "--clobber", *assets],
        check=True,
    )
    print(json.dumps({"draft_release": release, "assets": len(assets)}))


def parser() -> argparse.ArgumentParser:
    root = _project_root()
    settings = get_settings()
    command = argparse.ArgumentParser(prog="assessorai-data")
    subcommands = command.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build", help="Build a deterministic dataset release")
    build.add_argument("inputs", nargs="+", type=Path)
    build.add_argument("--release", required=True)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--sources", type=Path, default=root / "config" / "sources.json")
    build.add_argument("--embeddings", type=Path)
    build.add_argument("--max-records-per-asset", type=int, default=50_000)
    build.add_argument(
        "--allow-pending",
        action="store_true",
        help="Build a non-publishable staging preview with pending sources",
    )
    build.set_defaults(handler=_build)

    validate = subcommands.add_parser("validate-release")
    validate.add_argument("release_dir", type=Path)
    validate.add_argument("--require-publishable", action="store_true")
    validate.set_defaults(handler=_validate)

    migrate = subcommands.add_parser("migrate")
    migrate.add_argument("--database-url", default=settings.database_url)
    migrate.add_argument("--migrations", type=Path, default=root / "migrations")
    migrate.set_defaults(handler=_migrate)

    load = subcommands.add_parser("load-db")
    load.add_argument("release_dir", type=Path)
    load.add_argument("--database-url", default=settings.database_url)
    load.add_argument("--github-repository", default=settings.github_data_repository)
    load.add_argument("--allow-preview", action="store_true")
    load.set_defaults(handler=_load)

    upload = subcommands.add_parser("upload-draft")
    upload.add_argument("release_dir", type=Path)
    upload.add_argument("--repository", default=settings.github_data_repository)
    upload.set_defaults(handler=_upload_draft)
    return command


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
