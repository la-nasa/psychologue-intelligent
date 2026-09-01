"""Canaux de notification par organisation : résolution, repli politique, CRUD admin, RBAC."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.application import channels
from app.core.db import tenant_session
from app.core.errors import DomainError
from app.infrastructure.models import NotificationChannel


async def test_resolve_falls_back_to_policy_channels_as_log(make_org) -> None:
    org_id = await make_org()
    async with tenant_session(org_id) as session:
        resolved = await channels.resolve(session, organization_id=org_id, policy_channels=("clinician-console",))
    assert len(resolved) == 1
    assert resolved[0].kind == "log" and resolved[0].name == "clinician-console"


async def test_resolve_prefers_configured_channels(make_org, make_user) -> None:
    org_id = await make_org()
    actor = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=actor) as session:
        await channels.create_channel(
            session, organization_id=org_id, actor_id=actor, name="oncall", kind="email",
            target="oncall@clinic.example.com", request_id="r",
        )
    async with tenant_session(org_id) as session:
        resolved = await channels.resolve(session, organization_id=org_id, policy_channels=("clinician-console",))
    assert [(c.name, c.kind, c.target) for c in resolved] == [("oncall", "email", "oncall@clinic.example.com")]


async def test_channel_target_is_encrypted_at_rest(make_org, make_user) -> None:
    org_id = await make_org()
    actor = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=actor) as session:
        await channels.create_channel(
            session, organization_id=org_id, actor_id=actor, name="oncall", kind="email",
            target="secret-oncall@clinic.example.com", request_id="r",
        )
        raw = (await session.execute(select(NotificationChannel.target_enc))).scalar_one()
    assert "secret-oncall" not in raw


async def test_list_channels_hints_target_never_exposes_it(make_org, make_user) -> None:
    org_id = await make_org()
    actor = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=actor) as session:
        await channels.create_channel(
            session, organization_id=org_id, actor_id=actor, name="oncall", kind="email",
            target="oncall@clinic.example.com", request_id="r",
        )
        listed = await channels.list_channels(session, org_id)
    assert listed[0]["target_hint"] == "on***@clinic.example.com"
    assert "oncall@clinic.example.com" not in str(listed)


async def test_channels_are_isolated_between_organizations(make_org, make_user) -> None:
    org_a = await make_org()
    org_b = await make_org()
    actor = await make_user(org_a, f"a-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_a, user_id=actor) as session:
        await channels.create_channel(
            session, organization_id=org_a, actor_id=actor, name="oncall", kind="log", target="x", request_id="r",
        )
    async with tenant_session(org_b) as session:
        assert (await session.execute(select(NotificationChannel))).scalars().all() == []


async def test_admin_channel_endpoint_requires_privilege(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    resp = await client.post(
        "/api/v1/admin/notification-channels",
        json={"name": "x", "kind": "log", "target": "y"}, headers=h,
    )
    assert resp.status_code == 403  # un PATIENT n'est pas ADMIN


async def test_unknown_channel_kind_is_rejected(make_org, make_user) -> None:
    org_id = await make_org()
    actor = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=actor) as session:
        with pytest.raises(DomainError):
            await channels.create_channel(
                session, organization_id=org_id, actor_id=actor, name="x", kind="carrier-pigeon",
                target="y", request_id="r",
            )
