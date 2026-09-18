from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class MLOpsTracker:
    """MLflow registry adapter with explicit lifecycle operations.

    The local JSONL fallback is development-only and never claims registry
    promotion. Production must set MLFLOW_TRACKING_URI.
    """
    def __init__(self, tracking_uri: str | None = None, experiment: str = "psychologue-intelligent", path: Path = Path("work/mlops/runs.jsonl")):
        self.tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
        self.experiment = experiment
        self.path = path

    def _mlflow(self):
        if not self.tracking_uri:
            return None
        import mlflow  # type: ignore[import-not-found]
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment)
        return mlflow

    def log_run(self, name: str, params: dict[str, Any], metrics: dict[str, float], tags: dict[str, str] | None = None, artifacts: list[Path] | None = None) -> str:
        mlflow = self._mlflow()
        if mlflow:
            with mlflow.start_run(run_name=name) as run:
                mlflow.log_params(params); mlflow.log_metrics(metrics); mlflow.set_tags(tags or {})
                for artifact in artifacts or []:
                    mlflow.log_artifact(str(artifact))
                return run.info.run_id
        run_id = f"local-{int(time.time() * 1000)}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"run_id": run_id, "name": name, "params": params, "metrics": metrics, "tags": tags or {}, "created_at": time.time()}) + "\n")
        return run_id

    def register(self, run_id: str, model_uri: str, name: str) -> str:
        mlflow = self._mlflow()
        if not mlflow:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for registry operations")
        result = mlflow.register_model(model_uri, name)
        return result.version

    def transition(self, name: str, version: str, stage: str) -> None:
        if stage not in {"Staging", "Production", "Archived"}:
            raise ValueError("unsupported MLflow stage")
        mlflow = self._mlflow()
        if not mlflow:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for promotion")
        client = mlflow.MlflowClient()
        client.transition_model_version_stage(name=name, version=version, stage=stage, archive_existing_versions=stage == "Production")

    def set_alias(self, name: str, version: str, alias: str) -> None:
        mlflow = self._mlflow()
        if not mlflow:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for aliases")
        mlflow.MlflowClient().set_registered_model_alias(name, alias, version)
