from __future__ import annotations

from app.evaluation.agent_eval_runner import run_agent_evaluation


def main() -> None:
    rows = run_agent_evaluation()
    print(f"Generated {len(rows)} agent evaluation rows")


if __name__ == "__main__":
    main()
