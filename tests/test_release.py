from pathlib import Path

from assessorai_dados.canonical import load_source_policies, reconcile_records
from assessorai_dados.inputs import iter_input_records
from assessorai_dados.models import SourcePolicy
from assessorai_dados.release import build_release
from assessorai_dados.validation import validate_release

ROOT = Path(__file__).resolve().parents[1]


def test_release_assets_are_deterministic(tmp_path):
    policies = load_source_policies(ROOT / "config" / "sources.json")
    propositions, reconciliation = reconcile_records(
        iter_input_records([ROOT / "tests" / "fixtures" / "source.json"]),
        policies,
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = build_release(propositions, reconciliation, policies, first_dir, "2026.08.31")
    second = build_release(propositions, reconciliation, policies, second_dir, "2026.08.31")

    assert first.publishable is True
    first_hashes = {asset.name: asset.sha256 for asset in first.assets}
    second_hashes = {asset.name: asset.sha256 for asset in second.assets}
    assert first_hashes == second_hashes
    assert validate_release(first_dir)["propositions"] == 1


def test_preview_cannot_be_validated_as_publishable(tmp_path):
    policies = [
        SourcePolicy(
            id="pending-source",
            name="Pending source",
            house="Câmara Municipal de São Paulo",
        )
    ]
    propositions, reconciliation = reconcile_records(
        iter_input_records([ROOT / "tests" / "fixtures" / "source.json"]),
        policies,
        allow_pending=True,
    )
    release_dir = tmp_path / "preview"
    build_release(propositions, reconciliation, policies, release_dir, "2026.08.31")

    import pytest

    with pytest.raises(ValueError, match="redistribution clearance"):
        validate_release(release_dir, require_publishable=True)


def test_registered_sources_have_explicit_redistribution_review():
    policies = load_source_policies(ROOT / "config" / "sources.json")

    assert len(policies) == 18
    assert all(policy.redistribution_status == "allowed" for policy in policies)
    assert all(policy.redistribution_basis for policy in policies)
    assert all(policy.reviewed_at and policy.reviewed_by for policy in policies)
