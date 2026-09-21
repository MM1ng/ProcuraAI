from pathlib import Path

from app.decision.benchmark import DATASET_PATHS, load_intent_gold_set
from app.decision.schemas import IntentLabel


def test_decision_datasets_have_required_sizes_valid_fields_and_unique_ids():
    minimums = {"dev": 120, "test": 80, "hard": 40}
    for name, minimum in minimums.items():
        cases = load_intent_gold_set(DATASET_PATHS[name])
        assert len(cases) >= minimum
        assert len({case.id for case in cases}) == len(cases)
        assert all(case.text.strip() and case.label in IntentLabel for case in cases)
        assert all(case.language in {"zh", "en"} for case in cases)
        assert sum(case.language == "zh" for case in cases) / len(cases) >= 0.60


def test_decision_datasets_have_no_cross_dataset_exact_text_overlap():
    texts = {
        name: {case.text.strip().casefold() for case in load_intent_gold_set(path)}
        for name, path in DATASET_PATHS.items()
    }
    assert not (texts["dev"] & texts["test"])
    assert not (texts["dev"] & texts["hard"])
    assert not (texts["test"] & texts["hard"])


def test_production_workflow_does_not_import_the_offline_decision_package():
    root = Path(__file__).resolve().parents[1] / "app"
    for relative_path in (
        "agent/procurement_agent.py", "services/order_service.py",
        "services/stripe_payment_service.py", "services/plan_execution_guard.py",
    ):
        assert "app.decision" not in (root / relative_path).read_text(encoding="utf-8")
