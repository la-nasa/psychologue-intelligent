from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class MLOpsTracker:
    """MLflow tracking and registry facade.

    Production promotion requires a configured MLflow server. The JSONL mode is
    deliberately limited to development telemetry and cannot promote models.
    """
    VALID_STAGES = {"Staging", "Production", "Archived"}

    def __init__(self, tracking_uri: str | None = None, experiment: str = "psychologue-intelligent", path: Path = Path("work/mlops/runs.jsonl")):
        self.tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
        self.experiment = experiment
        self.path = path

    def _client(self):
        if not self.tracking_uri:
            return None, None
        import mlflow  # type: ignore[import-not-found]
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment)
        return mlflow, mlflow.MlflowClient()

    def log_run(self, name: str, params: dict[str, Any], metrics: dict[str, float], tags: dict[str, str] | None = None, artifacts: list[Path] | None = None) -> str:
        mlflow, _ = self._client()
        if mlflow:
            with mlflow.start_run(run_name=name) as run:
                mlflow.log_params(params); mlflow.log_metrics(metrics); mlflow.set_tags(tags or {})
                for artifact in artifacts or []:
                    mlflow.log_artifact(str(artifact))
                return run.info.run_id
        run_id = f"local-{int(time.time() * 1000)}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"run_id": run_id, "name": name, "params": params, "metrics": metrics, "tags": tags or {}, "created_at": time.time()}, ensure_ascii=False) + "\n")
        return run_id

    def register_model(self, run_id: str, artifact_path: str, registered_name: str) -> str:
        mlflow, _ = self._client()
        if not mlflow:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for registry operations")
        result = mlflow.register_model(f"runs:/{run_id}/{artifact_path}", registered_name)
        return str(result.version)

    def promote(self, registered_name: str, version: str, stage: str, alias: str | None = None) -> None:
        if stage not in self.VALID_STAGES:
            raise ValueError("unsupported MLflow stage")
        mlflow, client = self._client()
        if not mlflow or not client:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for promotion")
        client.transition_model_version_stage(name=registered_name, version=version, stage=stage, archive_existing_versions=stage == "Production")
        if alias:
            client.set_registered_model_alias(registered_name, alias, version)

    def rollback(self, registered_name: str, production_version: str, rollback_version: str) -> None:
        self.promote(registered_name, rollback_version, "Production", alias="champion")
        mlflow, client = self._client()
        if mlflow and client:
            client.set_registered_model_alias(registered_name, "rollback-from-" + production_version, production_version)

    def set_deployment_mode(self, registered_name: str, version: str, mode: str) -> None:
        if mode not in {"shadow", "canary", "production"}:
            raise ValueError("deployment mode must be shadow, canary or production")
        mlflow, client = self._client()
        if not mlflow or not client:
            raise RuntimeError("MLFLOW_TRACKING_URI is required for deployment metadata")
        client.set_model_version_tag(registered_name, version, "deployment_mode", mode)
