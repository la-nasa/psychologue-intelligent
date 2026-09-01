"""PHQ-9 (master prompt §8, §136) : scoring, item-9 isolé -> alerte, historique,
tendance, rappels, contrôle d'accès."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.ai.prompt import build_messages
from app.application import assessment
from app.core.db import system_session, tenant_session
from app.domain.assessment.phq9 import Phq9Result, score, severity_band
from app.infrastructure.models import Alert, Phq9Assessment

# --- scoring pur ---


def test_score_totals_and_isolates_item9() -> None:
    r = score([0, 1, 2, 3, 0, 1, 2, 3, 2])
    assert isinstance(r, Phq9Result)
    assert r.total_score == 14 and r.item9_score == 2 and r.severity_band == "modérée"


@pytest.mark.parametrize("answers", [[0] * 8, [0] * 10, [0, 1, 2, 3, 4, 0, 0, 0, 0], [0, 1, 2, 3, 0, 1, 2, 3, -1]])
def test_score_rejects_malformed_answers(answers) -> None:
    with pytest.raises(ValueError):
        score(answers)


def test_score_rejects_booleans() -> None:
    with pytest.raises(ValueError):
        score([True, False, 0, 0, 0, 0, 0, 0, 0])  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("total", "band"),
    [(0, "minimale"), (4, "minimale"), (5, "légère"), (9, "légère"), (10, "modérée"), (14, "modérée"),
     (15, "modérément sévère"), (19, "modérément sévère"), (20, "sévère"), (27, "sévère")],
)
def test_severity_bands_match_published_thresholds(total, band) -> None:
    assert severity_band(total) == band


# --- soumission + alerte item-9 ---


async def _patient(client: AsyncClient, slug: str, email: str) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _count(model) -> int:
    async with system_session() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_calm_phq9_persists_without_an_alert(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/assessments/phq9", json={"answers": [0] * 9}, headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["total_score"] == 0 and body["severity_band"] == "minimale"
    assert body["alert_level"] is None and body["alert_created"] is False
    assert await _count(Alert) == 0
    assert await _count(Phq9Assessment) == 1


async def test_item9_two_or_more_opens_a_red_alert(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/assessments/phq9", json={"answers": [0, 0, 0, 0, 0, 0, 0, 0, 2]}, headers=h)
    assert r.json()["alert_level"] == "RED" and r.json()["alert_created"] is True
    async with system_session() as s:
        alert = (await s.execute(select(Alert))).scalar_one()
    assert alert.level == "RED" and alert.source == "ASSESSMENT"
    assert alert.assessment_id is not None and alert.crisis_event_id is None


async def test_item9_one_opens_an_orange_alert(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/assessments/phq9", json={"answers": [0, 0, 0, 0, 0, 0, 0, 0, 1]}, headers=h)
    assert r.json()["alert_level"] == "ORANGE" and r.json()["alert_created"] is True


async def test_high_total_without_item9_opens_an_orange_alert(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/assessments/phq9", json={"answers": [3, 3, 3, 3, 3, 2, 0, 3, 0]}, headers=h)  # total 20
    assert r.json()["total_score"] == 20 and r.json()["alert_level"] == "ORANGE"


async def test_moderate_total_without_item9_does_not_alert(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/assessments/phq9", json={"answers": [2, 2, 2, 2, 2, 2, 1, 0, 0]}, headers=h)  # total 13
    assert r.json()["alert_level"] is None
    assert await _count(Alert) == 0


async def test_answers_are_encrypted_at_rest(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    await client.post("/api/v1/assessments/phq9", json={"answers": [1, 2, 3, 0, 1, 2, 3, 0, 0]}, headers=h)
    async with system_session() as s:
        raw = (await s.execute(select(Phq9Assessment.answers_enc))).scalar_one()
    assert "[1, 2, 3" not in raw and "1,2,3" not in raw


# --- validation via l'API ---


async def test_wrong_answer_count_is_422(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    assert (await client.post("/api/v1/assessments/phq9", json={"answers": [0] * 8}, headers=h)).status_code == 422


async def test_out_of_range_answer_is_400(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/assessments/phq9", json={"answers": [0, 0, 0, 0, 0, 0, 0, 0, 7]}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "invalid_phq9"


async def test_submission_is_rate_limited(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    codes = [
        (await client.post("/api/v1/assessments/phq9", json={"answers": [0] * 9}, headers=h)).status_code
        for _ in range(9)
    ]
    assert codes.count(201) == 6 and codes[-1] == 429  # limite = 6/h en test


# --- historique / tendance / accès ---


async def test_history_and_trend(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    await client.post("/api/v1/assessments/phq9", json={"answers": [2, 2, 2, 2, 2, 2, 2, 0, 0]}, headers=h)  # 14
    await client.post("/api/v1/assessments/phq9", json={"answers": [1, 1, 1, 1, 1, 0, 0, 0, 0]}, headers=h)  # 5

    hist = (await client.get("/api/v1/assessments/phq9", headers=h)).json()["items"]
    assert [x["total_score"] for x in hist] == [5, 14]  # plus récent d'abord

    tr = (await client.get("/api/v1/assessments/phq9/trend", headers=h)).json()
    assert tr["latest"]["total_score"] == 5 and tr["previous"]["total_score"] == 14
    assert tr["delta"] == -9 and tr["direction"] == "improving"


async def test_history_is_own_only(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    ha = await _patient(client, "acme", "a@acme.example.com")
    hb = await _patient(client, "acme", "b@acme.example.com")
    submitted = await client.post("/api/v1/assessments/phq9", json={"answers": [1] * 9}, headers=ha)
    aid = submitted.json()["id"]
    assert (await client.get("/api/v1/assessments/phq9", headers=hb)).json()["items"] == []
    assert (await client.get(f"/api/v1/assessments/phq9/{aid}/answers", headers=hb)).status_code == 404
    assert (await client.get(f"/api/v1/assessments/phq9/{aid}/answers", headers=ha)).json()["answers"] == [1] * 9


async def test_assessments_are_isolated_between_organizations(client: AsyncClient, make_org) -> None:
    await make_org("a")
    await make_org("b")
    ha = await _patient(client, "a", "p@a.example.com")
    await client.post("/api/v1/assessments/phq9", json={"answers": [1] * 9}, headers=ha)
    hb = await _patient(client, "b", "p@b.example.com")
    assert (await client.get("/api/v1/assessments/phq9", headers=hb)).json()["items"] == []


# --- bande de sévérité -> contexte de conversation ---


async def test_latest_severity_band_helper(make_org, make_user) -> None:
    org_id = await make_org()
    user_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=user_id) as session:
        assert await assessment.latest_severity_band(session, user_id) is None
        session.add(
            Phq9Assessment(
                id=uuid.uuid4(), organization_id=org_id, user_id=user_id, instrument_version="PHQ-9-1",
                answers_enc="x", total_score=16, item9_score=0,
            )
        )
        await session.flush()
        assert await assessment.latest_severity_band(session, user_id) == "modérément sévère"


def test_severity_band_is_woven_into_the_prompt_never_the_raw_score() -> None:
    system = build_messages("bonjour", {"phq9_severity_band": "modérée"})[0]["content"]
    assert "modérée" in system
    assert "ne jamais mentionner" in system  # instruction de discrétion


# --- rappels ---


async def test_schedule_and_list_reminder(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    due = (dt.datetime.now(dt.UTC) + dt.timedelta(days=14)).isoformat()
    assert (await client.post("/api/v1/assessments/reminders", json={"due_at": due}, headers=h)).status_code == 201
    items = (await client.get("/api/v1/assessments/reminders", headers=h)).json()["items"]
    assert len(items) == 1 and items[0]["status"] == "PENDING"


async def test_past_reminder_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    past = (dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).isoformat()
    r = await client.post("/api/v1/assessments/reminders", json={"due_at": past}, headers=h)
    assert r.status_code == 400
