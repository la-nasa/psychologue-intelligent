"""Reprise de notification avec backoff + lettre morte (threat-model-v2 TH-06/TM-08).
Porté de v1 `tests/test_crisis_pipeline.py::NotificationRetryTests`."""
from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai.providers.keyword_risk import KeywordRiskModel
from app.application.notifications import (
    MAX_ATTEMPTS,
    MAX_TOTAL_ATTEMPTS,
    retry_pending_notifications,
)
from app.application.safety import SafetyConfig, evaluate_incoming_message
from app.core.db import tenant_session
from app.domain.safety.policy import load_crisis_policy, load_crisis_rules, load_response_templates
from app.infrastructure.models import Notification

_DIR = Path("config/policies")
_CONFIG = SafetyConfig(
    policy=dataclasses.replace(
        load_crisis_policy(_DIR / "crisis-policy-v1.json"), notification_channels=("clinician-console",)
    ),
    rules=load_crisis_rules(_DIR / "crisis-rules-v1.json"),
    templates=load_response_templates(_DIR / "response-templates-v1.json"),
)


class FlakyProvider:
    """Échoue à chaque appel jusqu'à (et y compris) `succeed_on` ; ne réussit
    jamais si `succeed_on` est None. Simule une panne de canal puis une reprise."""

    def __init__(self, succeed_on: int | None = None) -> None:
        self.succeed_on = succeed_on
        self.calls = 0

    async def send(self, channel: str, target: str, payload: dict) -> str:
        self.calls += 1
        if self.succeed_on is not None and self.calls >= self.succeed_on:
            return f"flaky-ref-{self.calls}"
        raise RuntimeError("simulated provider outage")


@pytest.fixture
async def patient(make_org, make_user):
    org_id = await make_org()
    patient_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:8]}@x.example.com")
    return org_id, patient_id


async def _seed_failed_notification(org_id: uuid.UUID, patient_id: uuid.UUID, provider) -> None:
    async with tenant_session(org_id) as session:
        await evaluate_incoming_message(
            session, organization_id=org_id, patient_id=patient_id,
            text="plan suicidaire", message_reference=f"seed-{uuid.uuid4().hex[:8]}",
            config=_CONFIG, risk_model=KeywordRiskModel(), notification_provider=provider, request_id="seed",
        )


async def test_failed_notification_past_backoff_window_is_retried_and_can_succeed(patient) -> None:
    org_id, patient_id = patient
    await _seed_failed_notification(org_id, patient_id, FlakyProvider(succeed_on=None))

    async with tenant_session(org_id) as session:
        row = (await session.execute(select(Notification))).scalar_one()
        assert row.delivery_status == "FAILED"
        assert row.attempt_count == MAX_ATTEMPTS
        assert row.next_retry_at is not None

    # fenêtre de backoff pas encore écoulée : retenter "maintenant" ne change rien
    async with tenant_session(org_id) as session:
        assert await retry_pending_notifications(session, provider=FlakyProvider(None), request_id="too-soon") == []

    # une fois la fenêtre passée, un fournisseur redevenu sain réussit
    future = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    async with tenant_session(org_id) as session:
        outcomes = await retry_pending_notifications(
            session, provider=FlakyProvider(succeed_on=1), request_id="recovered", now=future
        )
        assert len(outcomes) == 1 and outcomes[0].status == "SENT"
        row = (await session.execute(select(Notification))).scalar_one()
        assert row.delivery_status == "SENT"
        assert row.next_retry_at is None


async def test_notification_failing_past_max_total_attempts_is_dead_lettered(patient) -> None:
    org_id, patient_id = patient
    await _seed_failed_notification(org_id, patient_id, FlakyProvider(succeed_on=None))

    moment = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    for _ in range(MAX_TOTAL_ATTEMPTS - MAX_ATTEMPTS):
        async with tenant_session(org_id) as session:
            outcomes = await retry_pending_notifications(
                session, provider=FlakyProvider(None), request_id="loop", now=moment
            )
            assert len(outcomes) == 1
        moment += dt.timedelta(days=1)

    async with tenant_session(org_id) as session:
        row = (await session.execute(select(Notification))).scalar_one()
        assert row.delivery_status == "FAILED"
        assert row.attempt_count == MAX_TOTAL_ATTEMPTS
        assert row.next_retry_at is None  # lettre morte : plus aucune planification

        # une ligne en lettre morte n'est plus jamais reprise, aussi loin dans le futur soit-on
        outcomes = await retry_pending_notifications(
            session, provider=FlakyProvider(None), request_id="after-dead-letter",
            now=moment + dt.timedelta(days=365),
        )
        assert outcomes == []
