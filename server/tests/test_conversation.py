from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select


async def _patient(client: AsyncClient, slug: str, email: str, *, care: bool = True) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if care:
        await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=h)
    return h


async def test_starting_a_conversation_requires_care_consent(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com", care=False)
    assert (await client.post("/api/v1/conversations", headers=h)).status_code == 403
    await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=h)
    assert (await client.post("/api/v1/conversations", headers=h)).status_code == 201


async def test_conversation_is_idempotent_while_active(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    a = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    b = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    assert a == b


async def test_green_message_gets_a_generated_reply(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    r = await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "Bonjour, ça va plutôt bien aujourd'hui."}, headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["decision_level"] == "GREEN"
    assert body["assistant_message"]["generation_path"] == "FAST"
    assert body["assistant_message"]["provider"] == "local"
    assert body["assistant_message"]["content"]


async def test_red_message_gets_the_fixed_template_and_opens_an_alert(client: AsyncClient, make_org) -> None:
    from app.core.db import system_session
    from app.infrastructure.models import Alert

    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    r = await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "j'ai un plan suicidaire"}, headers=h)
    body = r.json()
    assert body["decision_level"] == "RED"
    assert body["assistant_message"]["generation_path"] == "TEMPLATE"
    assert body["assistant_message"]["provider"] is None
    assert "professionnel" in body["assistant_message"]["content"]

    async with system_session() as session:
        assert (await session.execute(select(Alert))).scalars().first() is not None


async def test_history_is_chronological_and_decrypted(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "premier message"}, headers=h)
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "deuxième message"}, headers=h)
    items = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()["items"]
    assert [i["author_type"] for i in items] == ["PATIENT", "ASSISTANT", "PATIENT", "ASSISTANT"]
    assert items[0]["content"] == "premier message"
    assert [i["sequence_no"] for i in items] == [1, 2, 3, 4]


async def test_message_content_is_encrypted_at_rest(client: AsyncClient, make_org) -> None:
    from app.core.db import system_session
    from app.infrastructure.models import Message

    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "detail tres personnel"}, headers=h)
    async with system_session() as session:
        rows = (await session.execute(select(Message.content_enc))).scalars().all()
    assert rows and all("detail tres personnel" not in enc for enc in rows)


async def test_cannot_post_to_another_patients_conversation(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    ha = await _patient(client, "acme", "a@acme.example.com")
    hb = await _patient(client, "acme", "b@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=ha)).json()["id"]
    r = await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "coucou"}, headers=hb)
    assert r.status_code == 404


async def test_conversations_are_isolated_between_organizations(client: AsyncClient, make_org) -> None:
    await make_org("a")
    await make_org("b")
    ha = await _patient(client, "a", "p@x.example.com")
    hb = await _patient(client, "b", "p@x.example.com")
    cid = (await client.post("/api/v1/conversations", headers=ha)).json()["id"]
    assert (await client.get(f"/api/v1/conversations/{cid}/messages", headers=hb)).status_code == 404


async def test_message_rate_limit(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    codes = set()
    for _ in range(35):
        codes.add((await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "coucou"}, headers=h)).status_code)
    assert 429 in codes


async def test_empty_message_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    assert (await client.post(f"/api/v1/conversations/{cid}/messages", json={"text": ""}, headers=h)).status_code == 422
