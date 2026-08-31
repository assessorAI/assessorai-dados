from pathlib import Path

from assessorai_dados.canonical import load_source_policies, reconcile_records
from assessorai_dados.inputs import iter_input_records
from assessorai_dados.models import SourcePolicy

ROOT = Path(__file__).resolve().parents[1]


def test_reconcile_is_deterministic_and_merges_duplicates():
    policies = load_source_policies(ROOT / "config" / "sources.json")
    inputs = [ROOT / "tests" / "fixtures" / "source.json"]
    first, first_log = reconcile_records(iter_input_records(inputs), policies, allow_pending=True)
    second, second_log = reconcile_records(iter_input_records(inputs), policies, allow_pending=True)

    assert first == second
    assert first_log == second_log
    assert len(first) == 1
    assert [item.action for item in first_log] == ["published", "deduplicated"]
    assert first[0].authors == ["Vereadora Ana", "Vereador Bruno"]
    assert first[0].full_text.startswith("Art. 1º")


def test_pending_source_is_quarantined_by_default():
    policies = [
        SourcePolicy(
            id="pending-source",
            name="Pending source",
            house="Câmara Municipal de São Paulo",
        )
    ]
    inputs = [ROOT / "tests" / "fixtures" / "source.json"]
    propositions, log = reconcile_records(iter_input_records(inputs), policies)

    assert propositions == []
    assert len(log) == 2
    assert all(item.action == "quarantined" for item in log)
    assert all(item.reason == "redistribution_pending" for item in log)
