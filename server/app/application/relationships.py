"""Relations patient-clinicien (master prompt §33, §34).

Porté de v1 `backend/app/clinician.py` (`create_relationship`, `end_relationship`,
`has_active_relationship`). C'est la porte d'accès unique d'un clinicien au
dossier d'un patient : `require_active_relationship` est appelée par **chaque**
lecture de dossier et **chaque** action sur alerte côté clinicien.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.infrastructure.models import PatientClinicianRelationship, Profile, Role, User, UserRole

_CLINICIAN_ROLES = ("PSYCHOLOGIST", "CLINICAL_SUPERVISOR")


async def _roles_of(session: AsyncSession, user_id: uuid.UUID) -> frozenset[str]:
    rows = await session.execute(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    )
    return frozenset(rows.scalars().all())


async def _active_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return (
        await session.execute(
            select(User).where(User.id == user_id, User.status == "ACTIVE", User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


async def create_relationship(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    clinician_id: uuid.UUID,
    request_id: str,
) -> uuid.UUID:
    if patient_id == clinician_id:
        raise ConflictError("patient and clinician must be different users", code="invalid_relationship")

    patient = await _active_user(session, patient_id)
    clinician = await _active_user(session, clinician_id)
    if patient is None or clinician is None:
        raise NotFoundError("patient or clinician not found in this organization")

    if "PATIENT" not in await _roles_of(session, patient_id):
        raise ConflictError("target is not a patient", code="not_a_patient")
    if not (await _roles_of(session, clinician_id)).intersection(_CLINICIAN_ROLES):
        raise ConflictError("target is not a clinician", code="not_a_clinician")

    existing = (
        await session.execute(
            select(PatientClinicianRelationship).where(
                PatientClinicianRelationship.patient_id == patient_id,
                PatientClinicianRelationship.clinician_id == clinician_id,
                PatientClinicianRelationship.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    relationship_id = uuid.uuid4()
    session.add(
        PatientClinicianRelationship(
            id=relationship_id,
            organization_id=organization_id,
            patient_id=patient_id,
            clinician_id=clinician_id,
            status="ACTIVE",
            created_by=actor_id,
        )
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="relationship.create", resource_type="patient_clinician_relationship",
        resource_id=str(relationship_id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"patient_id": str(patient_id), "clinician_id": str(clinician_id)},
    )
    return relationship_id


async def end_relationship(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    relationship_id: uuid.UUID,
    request_id: str,
) -> None:
    row = (
        await session.execute(
            select(PatientClinicianRelationship).where(PatientClinicianRelationship.id == relationship_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("relationship not found")
    if row.status != "ACTIVE":
        raise ConflictError("relationship is not active", code="relationship_not_active")

    row.status = "ENDED"
    row.ended_at = dt.datetime.now(dt.UTC)
    row.ended_by = actor_id
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="relationship.end", resource_type="patient_clinician_relationship",
        resource_id=str(relationship_id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"patient_id": str(row.patient_id), "clinician_id": str(row.clinician_id)},
    )


async def has_active_relationship(
    session: AsyncSession, *, clinician_id: uuid.UUID, patient_id: uuid.UUID
) -> bool:
    row = (
        await session.execute(
            select(PatientClinicianRelationship.id).where(
                PatientClinicianRelationship.clinician_id == clinician_id,
                PatientClinicianRelationship.patient_id == patient_id,
                PatientClinicianRelationship.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def require_active_relationship(
    session: AsyncSession, *, clinician_id: uuid.UUID, patient_id: uuid.UUID
) -> None:
    if not await has_active_relationship(session, clinician_id=clinician_id, patient_id=patient_id):
        raise PermissionDeniedError("no active relationship with this patient")


async def list_users(
    session: AsyncSession, *, organization_id: uuid.UUID, role: str | None = None
) -> list[dict]:
    """Annuaire des comptes de l'organisation, pour l'écran admin de gestion des
    relations patient-clinicien (choisir un patient / un clinicien sans avoir à
    connaître son UUID de mémoire)."""
    stmt = (
        select(User.id, User.email_normalized, User.status, Profile.display_name)
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(User.organization_id == organization_id, User.deleted_at.is_(None))
        .order_by(User.email_normalized)
    )
    rows = (await session.execute(stmt)).all()

    roles_by_user: dict[uuid.UUID, list[str]] = {}
    role_rows = await session.execute(
        select(UserRole.user_id, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.organization_id == organization_id)
    )
    for user_id, code in role_rows.all():
        roles_by_user.setdefault(user_id, []).append(code)

    users: list[dict] = []
    for user_id, email, status, display_name in rows:
        user_roles = sorted(roles_by_user.get(user_id, []))
        if role is not None and role not in user_roles:
            continue
        users.append(
            {
                "id": str(user_id),
                "email": email,
                "display_name": display_name or "",
                "roles": user_roles,
                "status": status,
            }
        )
    return users


async def list_relationships(
    session: AsyncSession, *, organization_id: uuid.UUID, active_only: bool = False
) -> list[dict]:
    stmt = select(PatientClinicianRelationship).order_by(PatientClinicianRelationship.created_at.desc())
    if active_only:
        stmt = stmt.where(PatientClinicianRelationship.status == "ACTIVE")
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "patient_id": str(r.patient_id),
            "clinician_id": str(r.clinician_id),
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        }
        for r in rows
    ]
