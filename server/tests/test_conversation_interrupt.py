"""Interruption (barge-in texte) — le stream s'arrête, la réponse partielle est
persistée et marquée. Cible master prompt §48/§54 (interruption)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai.providers.external import ExternalLLMProvider
from app.ai.providers.keyword_risk import KeywordRiskModel
from app.ai.providers.local import LocalSupportiveResponder
from app.ai.routing.model_router import Providers
from app.application import consent
from app.application.conversation import get_messages, get_or_create_active_conversation, stream_turn
from app.application.notifications import LogNotificationProvider
from app.application.safety import SafetyConfig
from app.core.db import tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Message

_DIR = Path("config/policies")
_SAFETY = SafetyConfig(
    policy=load_crisis_policy(_DIR / "crisis-policy-v1.json"),
    rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
    templates=load_response_templates(_DIR / "response-templates-v1.json"),
)
_PROVIDERS = Providers(local=LocalSupportiveResponder(), external=ExternalLLMProvider())


@pytest.fixture
async def conversation(make_org, make_user):
    org_id = await make_org()
    patient_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    async with tenant_session(org_id, user_id=patient_id) as session:
        await consent.grant(session, organization_id=org_id, user_id=patient_id, purpose="CARE", request_id="r")
        convo = await get_or_create_active_conversation(
            session, organization_id=org_id, patient_id=patient_id, request_id="r"
        )
        cid = convo.id
    return org_id, patient_id, cid


async def test_interrupting_a_green_stream_persists_a_partial_marked_reply(conversation) -> None:
    org_id, patient_id, cid = conversation
    cancel = asyncio.Event()
    chunks: list[str] = []

    async with tenant_session(org_id, user_id=patient_id) as session:
        gen = stream_turn(
            session, organization_id=org_id, patient_id=patient_id, conversation_id=cid,
            text="raconte moi une histoire tres longue s'il te plait pour tester l'interruption du flux",
            safety_config=_SAFETY, risk_model=KeywordRiskModel(),
            notification_provider=LogNotificationProvider(), providers=_PROVIDERS, request_id="r", cancel=cancel,
        )
        assistant_final = None
        async for event in gen:
            if event["type"] == "assistant_chunk":
                chunks.append(event["text"])
                if len(chunks) == 1:
                    cancel.set()  # barge-in après le premier fragment
            elif event["type"] == "assistant_message":
                assistant_final = event

        # récupère le responder_version persisté
        row = (
            await session.execute(
                select(Message).where(Message.conversation_id == cid, Message.author_type == "ASSISTANT")
            )
        ).scalar_one()

    assert assistant_final is not None
    assert len(chunks) <= 3  # le flux s'est arrêté tôt, pas la réponse complète
    assert "interrupted" in (row.responder_version or "")

    # la réponse partielle est bien dans l'historique
    async with tenant_session(org_id, user_id=patient_id) as session:
        items = await get_messages(session, patient_id=patient_id, conversation_id=cid)
    assert [i["author_type"] for i in items] == ["PATIENT", "ASSISTANT"]
    assert items[1]["content"]  # non vide (au minimum un repli sûr)
