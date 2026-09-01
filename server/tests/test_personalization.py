"""PersonalizationEngine (master prompt §20-21, §27, §85).

Deux classes de tests exigées :
1. même message + profil différent  -> la réponse GREEN peut varier.
2. utilisateur différent + même condition de sécurité -> comportement de sécurité identique.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.ai.prompt import build_messages
from app.ai.providers.local import compose
from app.application import personalization
from app.core.db import tenant_session


async def _patient(client: AsyncClient, slug: str, email: str) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=h)
    return h


async def _set_prefs(client: AsyncClient, h: dict, **prefs) -> None:
    base = {"tone": "warm", "response_length": "medium", "question_frequency": "medium", "directiveness": "balanced"}
    base.update(prefs)
    assert (await client.put("/api/v1/profile/preferences", json=base, headers=h)).status_code == 204


# --- résolution du style ---


async def test_resolve_style_defaults_when_nothing_declared(make_org, make_user) -> None:
    org_id = await make_org()
    user_id = await make_user(org_id, f"p-{uuid.uuid4().hex[:6]}@x.example.com")
    async with tenant_session(org_id, user_id=user_id) as session:
        style = await personalization.resolve_style(session, user_id)
    assert style.tone == "warm" and style.response_length == "medium" and style.active_goals == ()


async def test_resolve_style_reflects_declared_preferences_and_goals(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    await _set_prefs(client, h, tone="direct", response_length="short", question_frequency="low")
    await client.post("/api/v1/goals", json={"title": "améliorer mon sommeil"}, headers=h)

    me = (await client.get("/api/v1/me", headers=h)).json()
    async with tenant_session(uuid.UUID(me["organization_id"]), user_id=uuid.UUID(me["id"])) as session:
        style = await personalization.resolve_style(session, uuid.UUID(me["id"]))
    assert style.tone == "direct" and style.response_length == "short" and style.question_frequency == "low"
    assert "améliorer mon sommeil" in style.active_goals


# --- classe 1 : même message, profil différent -> réponse GREEN différente ---


def _reply_for_style(style: dict) -> str:
    messages = build_messages("j'ai eu une semaine plutot calme, juste un peu de stress au travail", {"interaction_style": style})
    return compose(messages)


def test_same_message_produces_different_replies_for_different_profiles() -> None:
    terse = _reply_for_style(
        {"tone": "direct", "response_length": "short", "question_frequency": "low", "directiveness": "reflective"}
    )
    expansive = _reply_for_style(
        {"tone": "warm", "response_length": "detailed", "question_frequency": "high", "directiveness": "directive"}
    )
    assert terse != expansive
    assert len(terse) < len(expansive)
    assert "?" not in terse           # question_frequency=low
    assert "?" in expansive


async def test_same_message_different_profile_end_to_end(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    ha = await _patient(client, "acme", "a@acme.example.com")
    hb = await _patient(client, "acme", "b@acme.example.com")
    await _set_prefs(client, ha, response_length="short", question_frequency="low")
    await _set_prefs(client, hb, response_length="detailed", question_frequency="high", directiveness="directive")

    ca = (await client.post("/api/v1/conversations", headers=ha)).json()["id"]
    cb = (await client.post("/api/v1/conversations", headers=hb)).json()["id"]
    msg = {"text": "j'ai eu une semaine plutot calme, juste un peu de stress au travail"}
    ra = (await client.post(f"/api/v1/conversations/{ca}/messages", json=msg, headers=ha)).json()["assistant_message"]["content"]
    rb = (await client.post(f"/api/v1/conversations/{cb}/messages", json=msg, headers=hb)).json()["assistant_message"]["content"]
    assert ra != rb
    assert len(ra) < len(rb)


# --- classe 2 : condition de sécurité identique -> comportement identique ---


async def test_safety_reply_is_identical_regardless_of_profile(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    ha = await _patient(client, "acme", "a@acme.example.com")
    hb = await _patient(client, "acme", "b@acme.example.com")
    await _set_prefs(client, ha, tone="direct", response_length="short", question_frequency="low", directiveness="reflective")
    await _set_prefs(client, hb, tone="warm", response_length="detailed", question_frequency="high", directiveness="directive")

    ca = (await client.post("/api/v1/conversations", headers=ha)).json()["id"]
    cb = (await client.post("/api/v1/conversations", headers=hb)).json()["id"]
    crisis = {"text": "j'ai un plan suicidaire"}
    ra = (await client.post(f"/api/v1/conversations/{ca}/messages", json=crisis, headers=ha)).json()
    rb = (await client.post(f"/api/v1/conversations/{cb}/messages", json=crisis, headers=hb)).json()

    assert ra["decision_level"] == rb["decision_level"] == "RED"
    assert ra["assistant_message"]["content"] == rb["assistant_message"]["content"]  # gabarit fixe, mot pour mot
    assert ra["assistant_message"]["generation_path"] == rb["assistant_message"]["generation_path"] == "TEMPLATE"


# --- objectifs ---


async def test_goal_is_never_created_automatically(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "je voudrais mieux dormir"}, headers=h)
    assert (await client.get("/api/v1/goals", headers=h)).json()["items"] == []


async def test_goal_progress_and_completion(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    gid = (await client.post("/api/v1/goals", json={"title": "routine du soir"}, headers=h)).json()["id"]
    await client.post(f"/api/v1/goals/{gid}/progress", json={"value": 40, "note": "deux soirs cette semaine"}, headers=h)
    await client.post(f"/api/v1/goals/{gid}/progress", json={"value": 100}, headers=h)
    item = next(g for g in (await client.get("/api/v1/goals", headers=h)).json()["items"] if g["id"] == gid)
    assert item["progress"] == 100 and item["status"] == "ACHIEVED"


async def test_goals_are_isolated_between_users(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    ha = await _patient(client, "acme", "a@acme.example.com")
    hb = await _patient(client, "acme", "b@acme.example.com")
    await client.post("/api/v1/goals", json={"title": "objectif de A"}, headers=ha)
    assert (await client.get("/api/v1/goals", headers=hb)).json()["items"] == []


async def test_progress_on_another_users_goal_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    ha = await _patient(client, "acme", "a@acme.example.com")
    hb = await _patient(client, "acme", "b@acme.example.com")
    gid = (await client.post("/api/v1/goals", json={"title": "objectif de A"}, headers=ha)).json()["id"]
    r = await client.post(f"/api/v1/goals/{gid}/progress", json={"value": 50}, headers=hb)
    assert r.status_code == 404


@pytest.mark.parametrize("bad", [{"value": 150}, {"value": -1}])
async def test_invalid_progress_value_is_rejected(client: AsyncClient, make_org, bad) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    gid = (await client.post("/api/v1/goals", json={"title": "x"}, headers=h)).json()["id"]
    assert (await client.post(f"/api/v1/goals/{gid}/progress", json=bad, headers=h)).status_code == 422
