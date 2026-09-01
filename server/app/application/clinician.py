"""Surface « plateforme clinicien » (master prompt §33, audit G-12).

Lecture seule + agrégats pour le tableau de bord :
- `overview` : Today's Overview (compteurs d'alertes ouvertes, SLA dépassés,
  file assignée au clinicien),
- `list_patients` : Patient List (patients suivis + dernier PHQ-9 + alertes
  ouvertes),
- `patient_timeline` : dossier d'un patient (PHQ-9 + alertes + actions) — jamais
  le contenu des conversations ni les réponses brutes au questionnaire,
- `list_alerts` : Alert Center, filtré par niveau / statut.

Toutes ces fonctions sont bornées aux patients avec lesquels le clinicien a une
relation `ACTIVE` (`relationships.require_active_relationship` pour l'accès
nominatif ; sous-requête sur les relations actives pour les listes).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import assessment, consent, patient_summary
from app.application.relationships import require_active_relationship
from app.core.errors import DomainError
from app.domain.assessment.phq9 import severity_band
from app.infrastructure.models import (
    Alert,
    AlertAction,
    Goal,
    PatientClinicianRelationship,
    Phq9Assessment,
    Profile,
)

# Statuts « encore à traiter » (une alerte sort de la file quand elle est
# RESOLVED / CLOSED / CANCELLED).
_OPEN_STATUSES = ("OPEN", "NOTIFIED", "ACKNOWLEDGED", "IN_REVIEW", "ESCALATED")
_SLA_PENDING = ("OPEN", "NOTIFIED")
_FILTER_LEVELS = ("ORANGE", "RED")
_FILTER_STATUSES = (
    "OPEN", "NOTIFIED", "ACKNOWLEDGED", "IN_REVIEW", "ESCALATED", "RESOLVED", "CLOSED", "CANCELLED",
)


def _active_patient_ids(clinician_id: uuid.UUID):
    """SELECT des patient_id suivis activement — utilisé comme membre droit d'un
    `IN (...)` (peut renvoyer plusieurs lignes, ce n'est donc pas un scalaire)."""
    return select(PatientClinicianRelationship.patient_id).where(
        PatientClinicianRelationship.clinician_id == clinician_id,
        PatientClinicianRelationship.status == "ACTIVE",
    )


async def overview(session: AsyncSession, *, clinician_id: uuid.UUID, now: dt.datetime | None = None) -> dict:
    moment = now or dt.datetime.now(dt.UTC)
    patient_ids = _active_patient_ids(clinician_id)

    patients_followed = (
        await session.execute(
            select(func.count()).select_from(PatientClinicianRelationship).where(
                PatientClinicianRelationship.clinician_id == clinician_id,
                PatientClinicianRelationship.status == "ACTIVE",
            )
        )
    ).scalar_one()

    level_rows = (
        await session.execute(
            select(Alert.level, func.count())
            .where(Alert.patient_id.in_(patient_ids), Alert.status.in_(_OPEN_STATUSES))
            .group_by(Alert.level)
        )
    ).all()
    open_by_level: dict[str, int] = dict.fromkeys(_FILTER_LEVELS, 0)
    for level, count in level_rows:
        open_by_level[level] = count

    sla_breached = (
        await session.execute(
            select(func.count()).select_from(Alert).where(
                Alert.patient_id.in_(patient_ids),
                Alert.status.in_(_SLA_PENDING),
                Alert.sla_due_at.is_not(None),
                Alert.sla_due_at <= moment,
            )
        )
    ).scalar_one()

    assigned_to_me = (
        await session.execute(
            select(func.count()).select_from(Alert).where(
                Alert.assigned_clinician_id == clinician_id, Alert.status.in_(_OPEN_STATUSES)
            )
        )
    ).scalar_one()

    return {
        "patients_followed": patients_followed,
        "open_alerts": {
            "total": open_by_level["ORANGE"] + open_by_level["RED"],
            "red": open_by_level["RED"],
            "orange": open_by_level["ORANGE"],
        },
        "sla_breached": sla_breached,
        "assigned_to_me": assigned_to_me,
        "generated_at": moment.isoformat(),
    }


async def list_patients(session: AsyncSession, *, clinician_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(PatientClinicianRelationship.patient_id, Profile.display_name)
            .outerjoin(Profile, Profile.user_id == PatientClinicianRelationship.patient_id)
            .where(
                PatientClinicianRelationship.clinician_id == clinician_id,
                PatientClinicianRelationship.status == "ACTIVE",
            )
        )
    ).all()

    patients: list[dict] = []
    for patient_id, display_name in rows:
        latest = (
            await session.execute(
                select(Phq9Assessment.total_score, Phq9Assessment.item9_score, Phq9Assessment.completed_at)
                .where(Phq9Assessment.user_id == patient_id)
                .order_by(Phq9Assessment.completed_at.desc())
                .limit(1)
            )
        ).first()
        open_alerts = (
            await session.execute(
                select(func.count()).select_from(Alert).where(
                    Alert.patient_id == patient_id, Alert.status.in_(_OPEN_STATUSES)
                )
            )
        ).scalar_one()
        patients.append(
            {
                "patient_id": str(patient_id),
                "display_name": display_name or "",
                "latest_phq9": (
                    None
                    if latest is None
                    else {
                        "total_score": latest[0],
                        "item9_score": latest[1],
                        "severity_band": severity_band(latest[0]),
                        "completed_at": latest[2].isoformat(),
                    }
                ),
                "open_alert_count": open_alerts,
            }
        )
    patients.sort(key=lambda p: (-p["open_alert_count"], p["display_name"]))
    return patients


def alert_row(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "patient_id": str(alert.patient_id),
        "level": alert.level,
        "status": alert.status,
        "source": alert.source,
        "score": alert.score,
        "policy_version": alert.policy_version,
        "sla_due_at": alert.sla_due_at.isoformat() if alert.sla_due_at else None,
        "assigned_clinician_id": str(alert.assigned_clinician_id) if alert.assigned_clinician_id else None,
        "created_at": alert.created_at.isoformat(),
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }


async def list_alerts(
    session: AsyncSession,
    *,
    clinician_id: uuid.UUID,
    level: str | None = None,
    status: str | None = None,
) -> list[dict]:
    if level is not None and level not in _FILTER_LEVELS:
        raise DomainError("invalid level filter", code="invalid_filter")
    if status is not None and status not in _FILTER_STATUSES:
        raise DomainError("invalid status filter", code="invalid_filter")

    stmt = (
        select(Alert)
        .where(Alert.patient_id.in_(_active_patient_ids(clinician_id)))
        .order_by(Alert.created_at.desc())
    )
    if level is not None:
        stmt = stmt.where(Alert.level == level)
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [alert_row(a) for a in rows]


async def patient_timeline(
    session: AsyncSession, *, clinician_id: uuid.UUID, patient_id: uuid.UUID
) -> dict:
    await require_active_relationship(session, clinician_id=clinician_id, patient_id=patient_id)

    display_name = (
        await session.execute(select(Profile.display_name).where(Profile.user_id == patient_id))
    ).scalar_one_or_none()

    alerts = (
        await session.execute(
            select(Alert).where(Alert.patient_id == patient_id).order_by(Alert.created_at.desc())
        )
    ).scalars().all()
    alert_ids = [a.id for a in alerts]
    actions: list[dict] = []
    if alert_ids:
        action_rows = (
            await session.execute(
                select(AlertAction)
                .where(AlertAction.alert_id.in_(alert_ids))
                .order_by(AlertAction.created_at.desc())
            )
        ).scalars().all()
        actions = [
            {
                "id": str(a.id),
                "alert_id": str(a.alert_id),
                "actor_id": str(a.actor_id) if a.actor_id else None,
                "action": a.action,
                "justification": a.justification,
                "created_at": a.created_at.isoformat(),
            }
            for a in action_rows
        ]

    return {
        "patient_id": str(patient_id),
        "display_name": display_name or "",
        # Bandes de sévérité + score total + item 9 (signal de sûreté isolé) —
        # jamais les réponses brutes item par item, jamais le contenu des messages.
        "phq9_history": await assessment.history(session, patient_id),
        "phq9_trend": await assessment.trend(session, patient_id),
        "alerts": [alert_row(a) for a in alerts],
        "alert_actions": actions,
    }


async def patient_summary_for(
    session: AsyncSession, *, clinician_id: uuid.UUID, patient_id: uuid.UUID
) -> dict:
    await require_active_relationship(session, clinician_id=clinician_id, patient_id=patient_id)
    return (await patient_summary.build_summary(session, patient_id=patient_id)).to_dict()


async def patient_360(
    session: AsyncSession, *, clinician_id: uuid.UUID, patient_id: uuid.UUID
) -> dict:
    """Vue « Patient 360 » : identité + consentements + synthèse tracée + timeline
    + objectifs. Une seule porte : la relation `ACTIVE`. Aucun contenu déchiffré
    (ni message, ni mémoire, ni réponse brute de questionnaire)."""
    await require_active_relationship(session, clinician_id=clinician_id, patient_id=patient_id)

    display_name = (
        await session.execute(select(Profile.display_name).where(Profile.user_id == patient_id))
    ).scalar_one_or_none()
    goals = (
        await session.execute(
            select(Goal).where(Goal.user_id == patient_id).order_by(Goal.created_at.desc())
        )
    ).scalars().all()

    summary = await patient_summary.build_summary(session, patient_id=patient_id)
    timeline = await patient_timeline(session, clinician_id=clinician_id, patient_id=patient_id)
    return {
        "patient_id": str(patient_id),
        "display_name": display_name or "",
        "consents": await consent.list_for_user(session, patient_id),
        "summary": summary.to_dict(),
        "goals": [
            {"id": str(g.id), "title": g.title, "status": g.status, "created_at": g.created_at.isoformat()}
            for g in goals
        ],
        "phq9_history": timeline["phq9_history"],
        "phq9_trend": timeline["phq9_trend"],
        "alerts": timeline["alerts"],
        "alert_actions": timeline["alert_actions"],
    }
