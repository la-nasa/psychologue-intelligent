"""Mémoire dans le moteur de conversation : écriture épisodique GREEN, récupération
au tour suivant, oubli sur révocation de consentement (bout en bout)."""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.application import memory
from app.core.db import system_session, tenant_session
from app.infrastructure.models import Memory


async def _patient(client: AsyncClient, slug: str, email: str) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=h)
    return h


async def test_green_turn_writes_an_episodic_memory(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "je dors tres mal depuis des semaines"}, headers=h)

    async with system_session() as session:
        rows = (await session.execute(select(Memory))).scalars().all()
    assert len(rows) == 1
    assert rows[0].type == "EPISODIC" and rows[0].provenance == "USER_DECLARED"
    assert rows[0].source_message_id is not None


async def test_crisis_turn_does_not_write_a_memory(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "j'ai un plan suicidaire"}, headers=h)
    async with system_session() as session:
        assert (await session.execute(select(Memory))).scalars().all() == []


async def test_earlier_message_is_retrievable_as_context_on_a_later_turn(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "mon sommeil est catastrophique en ce moment"}, headers=h)
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "sinon le travail ça va plutot bien"}, headers=h)

    # au 3e tour, la mémoire pertinente sur le sommeil doit remonter
    async with system_session() as session:
        # user_id = celui du patient ; on le retrouve via la mémoire
        row = (await session.execute(select(Memory).limit(1))).scalar_one()
        results = await memory.retrieve(session, user_id=row.user_id, query_text="encore une nuit sans dormir", limit=2)
    assert results and "sommeil" in results[0]["content"]


async def test_revoking_care_consent_forgets_conversation_memory(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "je me sens vraiment isole ces jours ci"}, headers=h)

    async with system_session() as session:
        row = (await session.execute(select(Memory))).scalar_one()
        user_id, org_id = row.user_id, row.organization_id
        assert await memory.retrieve(session, user_id=user_id, query_text="isolement", limit=2)

    assert (await client.post("/api/v1/consents/revoke", json={"purpose": "CARE"}, headers=h)).status_code == 204

    async with tenant_session(org_id, user_id=user_id) as session:
        assert await memory.retrieve(session, user_id=user_id, query_text="isolement", limit=2) == []
        assert (await session.execute(select(Memory))).scalar_one().status == "REVOKED"
