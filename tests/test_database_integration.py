import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from assessorai_dados.canonical import load_source_policies, reconcile_records
from assessorai_dados.database import LegislativeRepository, apply_migrations, load_release
from assessorai_dados.inputs import iter_input_records
from assessorai_dados.models import SearchFilters
from assessorai_dados.release import build_release
from assessorai_dados.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not set")
def test_release_can_rebuild_search_database(tmp_path):
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url)
    apply_migrations(engine, ROOT / "migrations")

    policies = load_source_policies(ROOT / "config" / "sources.json")
    propositions, reconciliation = reconcile_records(
        iter_input_records([ROOT / "tests" / "fixtures" / "source.json"]),
        policies,
        allow_pending=True,
    )
    release_dir = tmp_path / "release"
    build_release(propositions, reconciliation, policies, release_dir, "2026.08.31")
    assert (
        load_release(
            engine,
            release_dir,
            "assessorAI/assessorai-dados",
            allow_preview=True,
        )
        == 1
    )

    settings = Settings(database_url=database_url, openai_api_key=None)
    repository = LegislativeRepository(engine, settings)
    search = repository.search(SearchFilters(query="dados abertos"))
    proposition_id = search.items[0]["id"]

    assert search.release == "2026.08.31"
    assert repository.get_proposition(proposition_id)["title"] == "Projeto de Lei 123/2025"
    assert repository.read_text(proposition_id, 0, 20)["next_offset"] == 20
    assert repository.get_release("latest")["version"] == "2026.08.31"
    assert repository.list_sources()[0]["redistribution_status"] == "pending"
