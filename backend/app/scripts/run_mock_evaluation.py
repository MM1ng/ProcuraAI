from __future__ import annotations

from app.evaluation.mock_eval_runner import run_mock_evaluation


def main() -> None:
    rows = run_mock_evaluation()
    print(f"Generated {len(rows)} mock evaluation rows")


if __name__ == "__main__":
    main()
