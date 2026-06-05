from __future__ import annotations


def ragas_available() -> bool:
    try:
        import ragas  # noqa: F401

        return True
    except Exception:
        return False


def describe_ragas_path() -> str:
    return (
        "Ragas can be connected by converting evaluation logs into question, "
        "answer, contexts and ground_truth columns. Mock metrics are used for "
        "local demos when no model credentials are configured."
    )
