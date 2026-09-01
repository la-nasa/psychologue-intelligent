from __future__ import annotations

import time
import uuid

import pytest

from app.application import account, mfa, profile
from app.core.db import tenant_session
from app.core.errors import DomainError
from app.core.security import _totp_at


@pytest.fixture
async def user(make_org, make_user):
    org_id = await make_org()
    user_id = await make_user(org_id, f"u-{uuid.uuid4().hex[:8]}@x.example.com")
    return org_id, user_id


async def test_save_profile_stamps_onboarding_and_survives_invalid_language(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        await profile.save_profile(
            session, organization_id=org_id, user_id=user_id,
            display_name="Alex", about_me="jardinage", language="klingon", request_id="r",
        )
        got = await profile.get_profile(session, user_id)
    assert got["language"] == "fr"  # langue inconnue -> défaut
    assert got["display_name"] == "Alex"
    assert got["about_me"] == "jardinage"
    assert got["onboarding_completed_at"] is not None


async def test_preferences_default_and_roundtrip(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        assert (await profile.get_preferences(session, user_id))["tone"] == "warm"
        await profile.save_preferences(
            session, organization_id=org_id, user_id=user_id,
            tone="direct", response_length="short", question_frequency="low", directiveness="directive", request_id="r",
        )
        again = await profile.get_preferences(session, user_id)
    assert again == {
        "tone": "direct", "response_length": "short", "question_frequency": "low", "directiveness": "directive"
    }


async def test_mfa_enroll_then_activate_then_reject_double(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        enrolled = await mfa.enroll(session, organization_id=org_id, user_id=user_id, request_id="r")
        secret = enrolled["secret"]
        with pytest.raises(DomainError):
            await mfa.activate(session, organization_id=org_id, user_id=user_id, code="000000", request_id="r")
        await mfa.activate(
            session, organization_id=org_id, user_id=user_id,
            code=_totp_at(secret, int(time.time()) // 30), request_id="r",
        )
        with pytest.raises(DomainError):
            await mfa.enroll(session, organization_id=org_id, user_id=user_id, request_id="r")


async def test_mfa_enroll_unknown_user_is_404() -> None:
    from app.core.db import system_session

    async with system_session() as session:
        with pytest.raises(DomainError) as exc:
            await mfa.enroll(session, organization_id=uuid.uuid4(), user_id=uuid.uuid4(), request_id="r")
    assert exc.value.status_code == 404


async def test_mfa_activate_without_enrolment_is_rejected(user) -> None:
    org_id, user_id = user
    async with tenant_session(org_id, user_id=user_id) as session:
        with pytest.raises(DomainError, match="enrol"):
            await mfa.activate(session, organization_id=org_id, user_id=user_id, code="123456", request_id="r")


async def test_request_deletion_is_idempotent(user) -> None:
    org_id, user_id = user
    from sqlalchemy import func, select

    from app.infrastructure.models import DeletionRequest

    async with tenant_session(org_id, user_id=user_id) as session:
        assert await account.request_deletion(session, organization_id=org_id, user_id=user_id, request_id="r") == "OPEN"
        assert await account.request_deletion(session, organization_id=org_id, user_id=user_id, request_id="r") == "OPEN"
        count = (await session.execute(select(func.count()).select_from(DeletionRequest))).scalar_one()
    assert count == 1
