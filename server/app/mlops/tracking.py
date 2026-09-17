"""Client de tracking/registry MLflow (ADR-011, Phase 17).

Best-effort par construction : la gouvernance des versions de modèle vit dans
la table locale `model_versions` (`app.mlops.registry`), qui reste la source
de vérité fonctionnelle. Ce module ne fait que miroiter cet état vers un
serveur MLflow externe pour la traçabilité/observabilité MLOps — si
`PI_MLFLOW_TRACKING_URI` est vide ou si le serveur est injoignable, toutes les
fonctions ici renvoient silencieusement `None` plutôt que de faire échouer une
action de gouvernance.
"""
from __future__ import annotations

import logging
import os

from app.core.config import get_settings

LOGGER = logging.getLogger("pi.mlops.tracking")

_EXPERIMENT_NAME = "psychologue-intelligent-v2"

# L'API par « stage » de MLflow est dépréciée depuis 2.9 au profit des alias,
# mais reste fonctionnelle dans la 2.20 utilisée ici (mlflow-skinny) — la plus
# simple à faire correspondre à nos 6 étapes de gouvernance (ADR-011 §"Stages
# du Model Registry") sans introduire un second concept.
_MLFLOW_STAGE_MAP = {
    "EXPERIMENTAL": "None",
    "STAGING": "Staging",
    "SHADOW": "Staging",
    "CANARY": "Staging",
    "PRODUCTION": "Production",
    "RETIRED": "Archived",
}


def _configured() -> bool:
    settings = get_settings()
    if not settings.mlflow_tracking_uri:
        return False
    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        if settings.mlflow_tracking_username:
            os.environ["MLFLOW_TRACKING_USERNAME"] = settings.mlflow_tracking_username
            os.environ["MLFLOW_TRACKING_PASSWORD"] = settings.mlflow_tracking_password
        return True
    except Exception:
        LOGGER.exception("mlflow client unavailable")
        return False


def register_version(
    *, name: str, version: str, stage: str, params: dict, tags: dict, notes: str
) -> tuple[str | None, str | None]:
    """Journalise une exécution puis enregistre une version dans le Model
    Registry MLflow. Renvoie (run_id, mlflow_model_version), ou (None, None)
    si MLflow n'est pas configuré ou injoignable."""
    if not _configured():
        return None, None
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_experiment(_EXPERIMENT_NAME)
        with mlflow.start_run(run_name=f"{name}-{version}") as run:
            mlflow.log_params(params)
            mlflow.set_tags({**tags, "stage": stage})
            mlflow.log_text(notes or "(aucune note)", "model_card.md")
            run_id = run.info.run_id

        client = MlflowClient()
        try:
            client.create_registered_model(name)
        except Exception:
            pass  # déjà enregistré — pas une erreur
        mv = client.create_model_version(name=name, source=f"runs:/{run_id}/model_card.md", run_id=run_id)
        return run_id, mv.version
    except Exception:
        LOGGER.exception("mlflow registration failed; local governance unaffected")
        return None, None


def transition_stage(*, name: str, mlflow_version: str | None, stage: str) -> None:
    if not mlflow_version or not _configured():
        return
    try:
        from mlflow.tracking import MlflowClient

        MlflowClient().transition_model_version_stage(
            name=name, version=mlflow_version, stage=_MLFLOW_STAGE_MAP.get(stage, "None")
        )
    except Exception:
        LOGGER.exception("mlflow stage transition failed; local governance unaffected")
