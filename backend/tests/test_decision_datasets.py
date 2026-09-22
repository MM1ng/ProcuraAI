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


def test_production_workflow_only_imports_the_audit_only_shadow_decision_entrypoints():
    root = Path(__file__).resolve().parents[1] / "app"
    for relative_path in (
        "services/order_service.py",
        "services/stripe_payment_service.py", "services/plan_execution_guard.py",
    ):
        assert "app.decision" not in (root / relative_path).read_text(encoding="utf-8")

    agent_source = (root / "agent/procurement_agent.py").read_text(encoding="utf-8")
    assert "from app.decision.gateway import dispatch_jev_shadow" in agent_source
    assert "from app.decision.shadow import authoritative_intent_label" in agent_source
    for forbidden_module in (
        "app.decision.benchmark",
        "app.decision.registry",
        "app.decision.providers.baseline",
        "app.decision.providers.von",
    ):
        assert forbidden_module not in agent_source
