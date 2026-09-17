"""Model Registry local (Phase 17, ADR-011).

`ModelVersion` est la source de vérité de gouvernance — miroir best-effort
vers MLflow via `app.mlops.tracking`. Aucune fonction ici ne déclenche un
entraînement ou un déploiement : ce module enregistre et fait transitionner
des VERSIONS déjà produites ailleurs (le moteur à règles / lexique actuel,
un futur modèle entraîné), avec une piste d'audit complète.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.infrastructure.models import ModelVersion
from app.mlops import tracking

STAGES = ("EXPERIMENTAL", "STAGING", "SHADOW", "CANARY", "PRODUCTION", "RETIRED")

# Progression de gouvernance (ADR-011) : une étape ne peut avancer que vers
# l'une de ces cibles, ou être retirée directement en cas de problème.
_NEXT_STAGE = {
    "EXPERIMENTAL": ("STAGING", "RETIRED"),
    "STAGING": ("SHADOW", "RETIRED"),
    "SHADOW": ("CANARY", "RETIRED"),
    "CANARY": ("PRODUCTION", "RETIRED"),
    "PRODUCTION": ("RETIRED",),
    "RETIRED": (),
}


def to_dict(row: ModelVersion) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "version": row.version,
        "stage": row.stage,
        "mlflow_run_id": row.mlflow_run_id,
        "mlflow_model_version": row.mlflow_model_version,
        "mlflow_linked": row.mlflow_run_id is not None,
        "notes": row.notes,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def register_version(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    version: str,
    notes: str,
    actor_id: uuid.UUID,
    request_id: str,
) -> ModelVersion:
    existing = (
        await session.execute(
            select(ModelVersion).where(
                ModelVersion.organization_id == organization_id,
                ModelVersion.name == name,
                ModelVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("this model version is already registered", code="model_version_exists")

    run_id, mlflow_version = tracking.register_version(
        name=name,
        version=version,
        stage="EXPERIMENTAL",
        params={"registered_by": str(actor_id), "organization_id": str(organization_id)},
        tags={"organization_id": str(organization_id)},
        notes=notes,
    )

    row = ModelVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        name=name,
        version=version,
        stage="EXPERIMENTAL",
        mlflow_run_id=run_id,
        mlflow_model_version=mlflow_version,
        notes=notes,
        registered_by=actor_id,
    )
    session.add(row)
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="model.register", resource_type="model_version",
        resource_id=str(row.id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"name": name, "version": version, "mlflow_linked": run_id is not None},
    )
    return row


async def list_versions(session: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(ModelVersion)
            .where(ModelVersion.organization_id == organization_id)
            .order_by(ModelVersion.created_at.desc())
        )
    ).scalars().all()
    return [to_dict(r) for r in rows]


async def _get(session: AsyncSession, *, organization_id: uuid.UUID, model_version_id: uuid.UUID) -> ModelVersion:
    row = (
        await session.execute(
            select(ModelVersion).where(
                ModelVersion.id == model_version_id, ModelVersion.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("model version not found")
    return row


async def promote(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    model_version_id: uuid.UUID,
    target_stage: str,
    actor_id: uuid.UUID,
    request_id: str,
) -> ModelVersion:
    if target_stage not in STAGES:
        raise DomainError("unknown stage", code="invalid_stage")
    row = await _get(session, organization_id=organization_id, model_version_id=model_version_id)
    if target_stage not in _NEXT_STAGE.get(row.stage, ()):
        raise DomainError(f"cannot go from {row.stage} to {target_stage} directly", code="invalid_stage_transition")

    previous_stage = row.stage
    row.stage = target_stage
    row.updated_at = dt.datetime.now(dt.UTC)
    await session.flush()
    tracking.transition_stage(name=row.name, mlflow_version=row.mlflow_model_version, stage=target_stage)
    await audit.record(
        session, request_id=request_id, action="model.promote", resource_type="model_version",
        resource_id=str(row.id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"from": previous_stage, "to": target_stage},
    )
    return row


async def rollback(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    model_version_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    request_id: str,
) -> ModelVersion:
    row = await _get(session, organization_id=organization_id, model_version_id=model_version_id)
    if row.stage not in ("CANARY", "PRODUCTION"):
        raise DomainError("only a canary or production version can be rolled back", code="invalid_rollback")

    previous_stage = row.stage
    row.stage = "RETIRED"
    stamp = dt.datetime.now(dt.UTC)
    row.notes = f"{row.notes}\n\n[ROLLBACK {stamp.isoformat()}] {reason}".strip()
    row.updated_at = stamp
    await session.flush()
    tracking.transition_stage(name=row.name, mlflow_version=row.mlflow_model_version, stage="RETIRED")
    await audit.record(
        session, request_id=request_id, action="model.rollback", resource_type="model_version",
        resource_id=str(row.id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"from": previous_stage, "reason": reason},
    )
    return row
