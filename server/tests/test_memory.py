"""MemoryService : retrieval, provenance, oubli (threat-model-v2 TV-04/TV-05)."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app.application import consent, memory
from app.core.db import tenant_session
from app.core.errors import DomainError
from app.infrastructure.models import Memory


@pytest.fixture
async def user(make_org, make_user):
    org_id = await make_org()
    user_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    return org_id, user_id


async def _remember(session, org_id, user_id, content, **kw):
    return await memory.remember(
        session, organization_id=org_id, user_id=user_id, content=content, request_id="r", **kw
    )


async def test_retrieval_ranks_the_topically_relevant_memory_first(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        await _remember(session, org_id, user_id, "je dors tres mal la nuit en ce moment")
        await _remember(session, org_id, user_id, "mon travail me stresse enormement ces temps ci")
        await _remember(session, org_id, user_id, "j'aime beaucoup faire de la randonnee le week-end")
        results = await memory.retrieve(session, user_id=user_id, query_text="je n'arrive pas a dormir", limit=3)
    assert results
    assert "dors" in results[0]["content"]


async def test_model_inferred_memory_requires_explicit_confidence(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        with pytest.raises(DomainError, match="confidence"):
            await _remember(session, org_id, user_id, "semble anxieux", provenance="MODEL_INFERRED")
        mid = await _remember(session, org_id, user_id, "semble anxieux", provenance="MODEL_INFERRED", confidence=0.4)
        row = (await session.execute(select(Memory).where(Memory.id == mid))).scalar_one()
        assert row.provenance == "MODEL_INFERRED" and row.confidence == 0.4


async def test_patient_cannot_create_a_clinician_validated_memory(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        with pytest.raises(DomainError, match="provenance"):
            await _remember(session, org_id, user_id, "fait", provenance="CLINICIAN_VALIDATED")


async def test_empty_memory_is_rejected(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        with pytest.raises(DomainError, match="empty"):
            await _remember(session, org_id, user_id, "   ")


async def test_revoked_memory_is_never_retrieved(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        await consent.grant(session, organization_id=org_id, user_id=user_id, purpose="CARE", request_id="r")
        await _remember(session, org_id, user_id, "je me sens seul le soir")
        assert await memory.retrieve(session, user_id=user_id, query_text="solitude le soir", limit=3)

        count = await memory.forget_for_consent(
            session, organization_id=org_id, user_id=user_id, purpose="CARE", request_id="r"
        )
        assert count == 1
        assert await memory.retrieve(session, user_id=user_id, query_text="solitude le soir", limit=3) == []

        row = (await session.execute(select(Memory))).scalar_one()
        assert row.status == "REVOKED"


async def test_expired_memory_is_never_retrieved(user) -> None:
    org_id, user_id = user
    past = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    async with tenant_session(org_id, user_id=user_id) as session:
        await _remember(session, org_id, user_id, "note temporaire sur mon rendez vous", expires_at=past)
        # exclue par la fenêtre d'expiration au retrieval, même sans passage du worker
        assert await memory.retrieve(session, user_id=user_id, query_text="rendez vous", limit=3) == []
        assert await memory.expire_due(session) == 1
        row = (await session.execute(select(Memory))).scalar_one()
        assert row.status == "EXPIRED"


async def test_memories_are_isolated_between_users(make_org, make_user) -> None:
    org_id = await make_org()
    a = await make_user(org_id, f"a-{uuid.uuid4().hex[:6]}@x.example.com")
    b = await make_user(org_id, f"b-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=a) as session:
        await _remember(session, org_id, a, "secret de A propos de son sommeil")
    async with tenant_session(org_id, user_id=b) as session:
        assert await memory.retrieve(session, user_id=b, query_text="sommeil", limit=3) == []


async def test_memories_are_isolated_between_organizations(make_org, make_user) -> None:
    org_a = await make_org()
    org_b = await make_org()
    ua = await make_user(org_a, "p@a.example.com")
    async with tenant_session(org_a, user_id=ua) as session:
        await _remember(session, org_a, ua, "contenu de l'organisation A")
    async with tenant_session(org_b) as session:
        assert (await session.execute(select(Memory))).scalars().all() == []
