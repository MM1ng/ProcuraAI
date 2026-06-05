from __future__ import annotations

from typing import Any


def log_metrics_to_mlflow(metrics: dict[str, Any]) -> bool:
    try:
        import mlflow

        with mlflow.start_run(run_name="enterprise-procurement-agent-mock-eval"):
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(key, value)
        return True
    except Exception:
        return False
