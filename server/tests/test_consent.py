from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.application import consent
from app.core.db import tenant_session
from app.core.errors import DomainError


async def _patient_token(client: AsyncClient, slug: str, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    return r.json()["access_token"]


async def test_grant_then_list_then_revoke(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    token = await _patient_token(client, "acme", "p@acme.example.com")
    h = {"Authorization": f"Bearer {token}"}

    assert (await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=h)).status_code == 204
    items = (await client.get("/api/v1/consents", headers=h)).json()["items"]
    care = [i for i in items if i["purpose"] == "CARE"]
    assert len(care) == 1 and care[0]["active"] is True and care[0]["version"] == "1"

    assert (await client.post("/api/v1/consents/revoke", json={"purpose": "CARE"}, headers=h)).status_code == 204
    items = (await client.get("/api/v1/consents", headers=h)).json()["items"]
    assert next(i for i in items if i["purpose"] == "CARE")["active"] is False


async def test_regranting_same_version_reactivates_not_duplicates(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _patient_token(client, 'acme', 'p@acme.example.com')}"}
    await client.post("/api/v1/consents", json={"purpose": "AI_EXTERNAL"}, headers=h)
    await client.post("/api/v1/consents/revoke", json={"purpose": "AI_EXTERNAL"}, headers=h)
    await client.post("/api/v1/consents", json={"purpose": "AI_EXTERNAL"}, headers=h)
    items = [i for i in (await client.get("/api/v1/consents", headers=h)).json()["items"] if i["purpose"] == "AI_EXTERNAL"]
    assert len(items) == 1 and items[0]["active"] is True


async def test_unknown_purpose_is_rejected_by_schema(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _patient_token(client, 'acme', 'p@acme.example.com')}"}
    r = await client.post("/api/v1/consents", json={"purpose": "NONSENSE"}, headers=h)
    assert r.status_code == 422


async def test_consents_are_isolated_between_organizations(client: AsyncClient, make_org) -> None:
    await make_org("a")
    await make_org("b")
    ha = {"Authorization": f"Bearer {await _patient_token(client, 'a', 'p@x.example.com')}"}
    hb = {"Authorization": f"Bearer {await _patient_token(client, 'b', 'p@x.example.com')}"}
    await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=ha)
    assert (await client.get("/api/v1/consents", headers=hb)).json()["items"] == []


async def test_has_active_consent_helper_tracks_grant_and_revoke(make_org, make_user) -> None:
    org_id = await make_org()
    user_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    async with tenant_session(org_id, user_id=user_id) as session:
        assert await consent.has_active_consent(session, user_id, "CARE") is False
        await consent.grant(session, organization_id=org_id, user_id=user_id, purpose="CARE", request_id="r")
        assert await consent.has_active_consent(session, user_id, "CARE") is True
        await consent.revoke(session, organization_id=org_id, user_id=user_id, purpose="CARE", request_id="r")
        assert await consent.has_active_consent(session, user_id, "CARE") is False


async def test_grant_rejects_unknown_purpose_at_domain_level(make_org, make_user) -> None:
    org_id = await make_org()
    user_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    async with tenant_session(org_id, user_id=user_id) as session:
        with pytest.raises(DomainError):
            await consent.grant(session, organization_id=org_id, user_id=user_id, purpose="BOGUS", request_id="r")


async def test_all_six_purposes_are_grantable(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _patient_token(client, 'acme', 'p@acme.example.com')}"}
    for purpose in ("CARE", "LEARNING", "AI_EXTERNAL", "VOICE", "ANALYTICS", "RESEARCH"):
        assert (await client.post("/api/v1/consents", json={"purpose": purpose}, headers=h)).status_code == 204
    active = {i["purpose"] for i in (await client.get("/api/v1/consents", headers=h)).json()["items"] if i["active"]}
    assert active == {"CARE", "LEARNING", "AI_EXTERNAL", "VOICE", "ANALYTICS", "RESEARCH"}
