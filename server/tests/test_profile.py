from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select


async def _token(client: AsyncClient, slug: str, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    return r.json()["access_token"]


async def test_default_profile_then_save_stamps_onboarding_once(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}

    default = (await client.get("/api/v1/profile", headers=h)).json()
    assert default == {"display_name": "", "about_me": "", "language": "fr", "onboarding_completed_at": None}

    assert (await client.post("/api/v1/profile", json={"display_name": "Alex", "about_me": "aime le jardinage", "language": "en"}, headers=h)).status_code == 204
    first = (await client.get("/api/v1/profile", headers=h)).json()
    assert first["display_name"] == "Alex"
    assert first["about_me"] == "aime le jardinage"
    assert first["language"] == "en"
    assert first["onboarding_completed_at"] is not None

    await client.post("/api/v1/profile", json={"display_name": "Alexandre", "about_me": "", "language": "fr"}, headers=h)
    second = (await client.get("/api/v1/profile", headers=h)).json()
    assert second["display_name"] == "Alexandre"
    assert second["onboarding_completed_at"] == first["onboarding_completed_at"]  # jamais réécrit


async def test_about_me_is_encrypted_at_rest(client: AsyncClient, make_org) -> None:
    from app.core.db import system_session
    from app.infrastructure.models import Profile

    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}
    await client.post("/api/v1/profile", json={"display_name": "Alex", "about_me": "secret medical detail", "language": "fr"}, headers=h)

    async with system_session() as session:
        row = (await session.execute(select(Profile))).scalar_one()
    assert row.about_me_enc is not None
    assert "secret medical detail" not in row.about_me_enc


async def test_preferences_default_then_update(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}
    assert (await client.get("/api/v1/profile/preferences", headers=h)).json()["tone"] == "warm"
    r = await client.put(
        "/api/v1/profile/preferences",
        json={"tone": "direct", "response_length": "short", "question_frequency": "low", "directiveness": "directive"},
        headers=h,
    )
    assert r.status_code == 204
    assert (await client.get("/api/v1/profile/preferences", headers=h)).json()["response_length"] == "short"


async def test_invalid_preference_value_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}
    r = await client.put(
        "/api/v1/profile/preferences",
        json={"tone": "aggressive", "response_length": "short", "question_frequency": "low", "directiveness": "directive"},
        headers=h,
    )
    assert r.status_code == 422


async def test_preferences_can_be_updated_a_second_time(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}
    await client.put(
        "/api/v1/profile/preferences",
        json={"tone": "direct", "response_length": "short", "question_frequency": "low", "directiveness": "directive"},
        headers=h,
    )
    r = await client.put(
        "/api/v1/profile/preferences",
        json={"tone": "warm", "response_length": "detailed", "question_frequency": "high", "directiveness": "reflective"},
        headers=h,
    )
    assert r.status_code == 204
    prefs = (await client.get("/api/v1/profile/preferences", headers=h)).json()
    assert prefs == {"tone": "warm", "response_length": "detailed", "question_frequency": "high", "directiveness": "reflective"}


async def test_profile_can_be_re_saved_after_onboarding(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}
    await client.post("/api/v1/profile", json={"display_name": "A", "about_me": "one", "language": "fr"}, headers=h)
    await client.post("/api/v1/profile", json={"display_name": "A", "about_me": "two", "language": "fr"}, headers=h)
    assert (await client.get("/api/v1/profile", headers=h)).json()["about_me"] == "two"


async def test_profile_is_isolated_between_organizations(client: AsyncClient, make_org) -> None:
    await make_org("a")
    await make_org("b")
    ha = {"Authorization": f"Bearer {await _token(client, 'a', 'p@x.example.com')}"}
    hb = {"Authorization": f"Bearer {await _token(client, 'b', 'p@x.example.com')}"}
    await client.post("/api/v1/profile", json={"display_name": "OrgA Person", "about_me": "", "language": "fr"}, headers=ha)
    assert (await client.get("/api/v1/profile", headers=hb)).json()["display_name"] == ""
