from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class MLOpsTracker:
    """MLflow adapter with a local JSONL fallback; no production import is mandatory."""

    def __init__(self, tracking_uri: str | None = None, path: Path = Path("work/mlops/runs.jsonl")):
        self.tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
        self.path = path

    def log_run(self, name: str, params: dict[str, Any], metrics: dict[str, float], tags: dict[str, str] | None = None) -> str:
        run_id = f"local-{int(time.time() * 1000)}"
        record = {"run_id": run_id, "name": name, "params": params, "metrics": metrics, "tags": tags or {}, "created_at": time.time(), "tracking_uri": self.tracking_uri}
        if self.tracking_uri:
            try:
                import mlflow  # type: ignore[import-not-found]
                with mlflow.start_run(run_name=name):
                    mlflow.log_params(params); mlflow.log_metrics(metrics); mlflow.set_tags(tags or {}); run_id = mlflow.active_run().info.run_id
                return run_id
            except Exception:
                pass
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return run_id
