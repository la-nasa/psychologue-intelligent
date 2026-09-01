"""Relations patient-clinicien (master prompt §33, §34) : création/rupture,
validation des rôles, porte d'accès `require_active_relationship`, RBAC admin,
isolation par organisation."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.application import relationships
from app.core.db import system_session, tenant_session
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.infrastructure.models import AuditLog, PatientClinicianRelationship


@pytest.fixture
async def org_with_actors(make_org, make_user):
    org_id = await make_org()
    admin = await make_user(org_id, f"admin-{uuid.uuid4().hex[:6]}@x.example.com", roles=("ADMIN",))
    patient = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    clinician = await make_user(org_id, f"c-{uuid.uuid4().hex[:6]}@x.example.com", roles=("PSYCHOLOGIST",))
    return org_id, admin, patient, clinician


async def test_create_then_gate_allows_the_clinician(org_with_actors) -> None:
    org_id, admin, patient, clinician = org_with_actors
    async with tenant_session(org_id, user_id=admin) as session:
        rid = await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin,
            patient_id=patient, clinician_id=clinician, request_id="r",
        )
    assert isinstance(rid, uuid.UUID)
    async with tenant_session(org_id, user_id=clinician) as session:
        assert await relationships.has_active_relationship(session, clinician_id=clinician, patient_id=patient)
        await relationships.require_active_relationship(session, clinician_id=clinician, patient_id=patient)


async def test_create_is_idempotent(org_with_actors) -> None:
    org_id, admin, patient, clinician = org_with_actors
    async with tenant_session(org_id, user_id=admin) as session:
        a = await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=clinician, request_id="r"
        )
    async with tenant_session(org_id, user_id=admin) as session:
        b = await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=clinician, request_id="r"
        )
    assert a == b
    async with system_session() as session:
        count = len((await session.execute(select(PatientClinicianRelationship))).scalars().all())
    assert count == 1


async def test_create_rejects_a_non_patient_or_non_clinician(org_with_actors) -> None:
    org_id, admin, patient, clinician = org_with_actors
    # clinicien en position de patient
    async with tenant_session(org_id, user_id=admin) as session:
        with pytest.raises(ConflictError):
            await relationships.create_relationship(
                session, organization_id=org_id, actor_id=admin,
                patient_id=clinician, clinician_id=clinician, request_id="r",
            )
    # patient en position de clinicien
    async with tenant_session(org_id, user_id=admin) as session:
        with pytest.raises(ConflictError):
            await relationships.create_relationship(
                session, organization_id=org_id, actor_id=admin,
                patient_id=patient, clinician_id=patient, request_id="r",
            )


async def test_create_rejects_unknown_user(org_with_actors) -> None:
    org_id, admin, patient, _clinician = org_with_actors
    async with tenant_session(org_id, user_id=admin) as session:
        with pytest.raises(NotFoundError):
            await relationships.create_relationship(
                session, organization_id=org_id, actor_id=admin,
                patient_id=patient, clinician_id=uuid.uuid4(), request_id="r",
            )


async def test_end_relationship_closes_the_gate(org_with_actors) -> None:
    org_id, admin, patient, clinician = org_with_actors
    async with tenant_session(org_id, user_id=admin) as session:
        rid = await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=clinician, request_id="r"
        )
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.end_relationship(
            session, organization_id=org_id, actor_id=admin, relationship_id=rid, request_id="r"
        )
    async with tenant_session(org_id, user_id=clinician) as session:
        assert not await relationships.has_active_relationship(session, clinician_id=clinician, patient_id=patient)
        with pytest.raises(PermissionDeniedError):
            await relationships.require_active_relationship(session, clinician_id=clinician, patient_id=patient)
    # rompre deux fois -> conflit
    async with tenant_session(org_id, user_id=admin) as session:
        with pytest.raises(ConflictError):
            await relationships.end_relationship(
                session, organization_id=org_id, actor_id=admin, relationship_id=rid, request_id="r"
            )


async def test_ending_then_recreating_is_allowed(org_with_actors) -> None:
    org_id, admin, patient, clinician = org_with_actors
    async with tenant_session(org_id, user_id=admin) as session:
        rid1 = await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=clinician, request_id="r"
        )
        await relationships.end_relationship(
            session, organization_id=org_id, actor_id=admin, relationship_id=rid1, request_id="r"
        )
    async with tenant_session(org_id, user_id=admin) as session:
        rid2 = await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=clinician, request_id="r"
        )
    assert rid1 != rid2


async def test_relationships_are_isolated_between_organizations(org_with_actors, make_org, make_user) -> None:
    org_a, admin_a, patient_a, clinician_a = org_with_actors
    async with tenant_session(org_a, user_id=admin_a) as session:
        await relationships.create_relationship(
            session, organization_id=org_a, actor_id=admin_a, patient_id=patient_a, clinician_id=clinician_a, request_id="r"
        )
    org_b = await make_org()
    async with tenant_session(org_b) as session:
        assert (await session.execute(select(PatientClinicianRelationship))).scalars().all() == []


async def test_audit_records_the_relationship_change(org_with_actors) -> None:
    org_id, admin, patient, clinician = org_with_actors
    async with tenant_session(org_id, user_id=admin) as session:
        await relationships.create_relationship(
            session, organization_id=org_id, actor_id=admin, patient_id=patient, clinician_id=clinician, request_id="r"
        )
    async with system_session() as session:
        actions = (await session.execute(select(AuditLog.action))).scalars().all()
    assert "relationship.create" in actions


# --- RBAC HTTP : l'endpoint admin refuse un non-admin ---


async def test_admin_relationship_endpoint_requires_privilege(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post(
        "/api/v1/auth/register",
        json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"},
    )
    r = await client.post(
        "/api/v1/auth/sessions",
        json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"},
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    resp = await client.post(
        "/api/v1/admin/relationships",
        json={"patient_id": str(uuid.uuid4()), "clinician_id": str(uuid.uuid4())}, headers=h,
    )
    assert resp.status_code == 403
    assert (await client.get("/api/v1/admin/relationships", headers=h)).status_code == 403
