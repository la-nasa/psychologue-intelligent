from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.core.db import tenant_session
from app.infrastructure.models import AuditLog, User


async def test_rls_hides_rows_from_another_organization(make_org, make_user) -> None:
    org_a = await make_org("a")
    org_b = await make_org("b")
    await make_user(org_a, "alice@a.example.com")
    await make_user(org_b, "bob@b.example.com")

    async with tenant_session(org_a) as session:
        emails = (await session.execute(select(User.email_normalized))).scalars().all()
    assert emails == ["alice@a.example.com"]

    async with tenant_session(org_b) as session:
        emails = (await session.execute(select(User.email_normalized))).scalars().all()
    assert emails == ["bob@b.example.com"]


async def test_write_scoped_to_other_org_is_blocked_by_rls(make_org, make_user) -> None:
    org_a = await make_org("a")
    org_b = await make_org("b")

    # Tenter d'insérer, depuis le contexte de A, une ligne portant l'organisation de B.
    with pytest.raises(Exception):  # noqa: B017 — RLS lève une erreur d'insertion
        async with tenant_session(org_a) as session:
            session.add(
                User(
                    id=uuid.uuid4(),
                    organization_id=org_b,
                    email_normalized="intruder@b.example.com",
                    password_hash="x",
                    status="ACTIVE",
                )
            )
            await session.flush()


async def test_session_guc_does_not_leak_between_pooled_connections(make_org, make_user) -> None:
    org_a = await make_org("a")
    org_b = await make_org("b")
    await make_user(org_a, "alice@a.example.com")

    # Première transaction scopée à A, puis une seconde scopée à B sur (potentiellement)
    # la même connexion du pool : SET LOCAL est réinitialisé au commit.
    async with tenant_session(org_a) as session:
        assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 1
    async with tenant_session(org_b) as session:
        assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 0


async def test_audit_rows_are_org_scoped_on_read(make_org) -> None:
    org_a = await make_org("a")
    org_b = await make_org("b")
    async with tenant_session(org_a) as session:
        session.add(AuditLog(id=uuid.uuid4(), request_id="r", organization_id=org_a, action="t", resource_type="t", outcome="SUCCESS"))
    async with tenant_session(org_b) as session:
        rows = (await session.execute(select(AuditLog))).scalars().all()
    assert rows == []


async def test_no_tenant_context_sees_nothing(make_org, make_user) -> None:
    org_a = await make_org("a")
    await make_user(org_a, "alice@a.example.com")
    # tenant_session avec un UUID aléatoire (aucune organisation) => 0 ligne visible.
    async with tenant_session(uuid.uuid4()) as session:
        assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 0
