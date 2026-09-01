"""Cycle de vie d'alerte + garde de concurrence (threat-model-v2 TV-15 / SEC-001).
Porté de v1 `tests/test_security.py::BusinessLogicRaceConditionTests` (transitions d'alerte)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application.alerts import transition_alert
from app.application.notifications import LogNotificationProvider
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.db import tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Alert, AlertAction

_DIR = Path("config/policies")
# Sans canal : l'alerte reste OPEN (pas de transition auto NOTIFIED) — ces tests
# portent sur la garde de concurrence, pas sur la notification. Le NOTIFIED
# automatique est couvert par test_alert_lifecycle.py.
_CONFIG = SafetyConfig(
    policy=load_crisis_policy(_DIR / "crisis-policy-v1.json"),
    rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
    templates=load_response_templates(_DIR / "response-templates-v1.json"),
)


@pytest.fixture
async def alert_ctx(make_org, make_user):
    org_id = await make_org()
    patient_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    clinician_id = await make_user(org_id, f"c-{uuid.uuid4().hex[:8]}@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org_id) as session:
        outcome = await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="plan suicidaire", message_reference=f"m-{uuid.uuid4().hex[:8]}",
            config=_CONFIG, risk_model=KeywordRiskModel(), notification_provider=LogNotificationProvider(),
            request_id="seed",
        )
    return org_id, outcome.alert_id, clinician_id


async def test_valid_transition_records_action_and_timestamp(alert_ctx) -> None:
    org_id, aid, clinician_id = alert_ctx
    async with tenant_session(org_id) as session:
        updated = await transition_alert(
            session, alert_id=aid, target="ACKNOWLEDGED", actor_id=clinician_id, justification="vu"
        )
        assert updated.status == "ACKNOWLEDGED"
        assert updated.acknowledged_at is not None
        actions = (await session.execute(select(AlertAction).where(AlertAction.alert_id == aid))).scalars().all()
        assert [a.action for a in actions] == ["ACKNOWLEDGED"]


async def test_invalid_transition_is_rejected(alert_ctx) -> None:
    org_id, aid, clinician_id = alert_ctx
    async with tenant_session(org_id) as session:
        with pytest.raises(ValueError, match="invalid alert transition"):
            await transition_alert(session, alert_id=aid, target="RESOLVED", actor_id=clinician_id, justification="x")


async def test_unknown_alert_is_rejected() -> None:
    from app.core.db import system_session

    async with system_session() as session:
        with pytest.raises(ValueError, match="alert not found"):
            await transition_alert(session, alert_id=uuid.uuid4(), target="ACKNOWLEDGED", actor_id=uuid.uuid4(), justification="x")


async def test_concurrent_conflicting_transitions_have_exactly_one_winner(alert_ctx) -> None:
    org_id, aid, clinician_id = alert_ctx

    async def go(target: str) -> str:
        async with tenant_session(org_id) as session:
            await transition_alert(session, alert_id=aid, target=target, actor_id=clinician_id, justification=target)
        return target

    results = await asyncio.gather(go("ACKNOWLEDGED"), go("CANCELLED"), return_exceptions=True)
    winners = [r for r in results if isinstance(r, str)]
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(winners) == 1
    assert len(losers) == 1 and isinstance(losers[0], ValueError)

    async with tenant_session(org_id) as session:
        alert = (await session.execute(select(Alert).where(Alert.id == aid))).scalar_one()
        assert alert.status == winners[0]
        # exactement une action enregistrée — pas de lost update sur un enregistrement de sûreté
        assert (await session.execute(select(func.count()).select_from(AlertAction).where(AlertAction.alert_id == aid))).scalar_one() == 1
