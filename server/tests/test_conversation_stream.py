from __future__ import annotations

import json

from httpx import AsyncClient


async def _patient(client: AsyncClient, slug: str, email: str) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post("/api/v1/consents", json={"purpose": "CARE"}, headers=h)
    return h


async def _collect_sse(client: AsyncClient, url: str, payload: dict, headers: dict) -> list[dict]:
    events: list[dict] = []
    async with client.stream("POST", url, json=payload, headers=headers) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))
    return events


async def test_green_stream_yields_user_chunks_then_assistant_message_then_done(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    events = await _collect_sse(client, f"/api/v1/conversations/{cid}/messages/stream", {"text": "bonjour, plutot une bonne journee"}, h)

    types = [e["type"] for e in events]
    assert types[0] == "user_message"
    assert "assistant_chunk" in types
    assert types[-2:] == ["assistant_message", "done"]

    final = next(e for e in events if e["type"] == "assistant_message")
    assert final["decision_level"] == "GREEN"
    streamed = "".join(e["text"] for e in events if e["type"] == "assistant_chunk")
    assert final["content"] == streamed  # ce qui a été streamé == ce qui est persisté


async def test_green_stream_reports_ttft_without_clinical_content(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p-ttft@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    events = await _collect_sse(
        client, f"/api/v1/conversations/{cid}/messages/stream", {"text": "bonjour, plutot une bonne journee"}, h
    )
    final = next(e for e in events if e["type"] == "assistant_message")
    assert final["decision_level"] == "GREEN"
    assert final["ttft_ms"] is not None
    assert final["total_ms"] is not None
    assert final["ttft_ms"] <= final["total_ms"]


async def test_red_never_invokes_the_local_generator(client: AsyncClient, make_org) -> None:
    from app.ai.routing.model_router import Providers
    from app.main import app

    original = app.state.providers
    calls = {"n": 0}

    class _Spy:
        name = "local"
        version = "spy"

        async def health_check(self) -> bool:
            return True

        async def stream(self, messages, *, max_tokens):  # noqa: ANN001
            calls["n"] += 1
            raise AssertionError("local generator must not run for RED")
            yield  # pragma: no cover — make this an async generator

    app.state.providers = Providers(local=_Spy(), external=original.external)
    try:
        await make_org("acme")
        h = await _patient(client, "acme", "p-spy@acme.example.com")
        cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
        events = await _collect_sse(
            client, f"/api/v1/conversations/{cid}/messages/stream", {"text": "je veux me tuer"}, h
        )
        final = next(e for e in events if e["type"] == "assistant_message")
        assert final["decision_level"] == "RED"
        assert final["generation_path"] == "TEMPLATE"
        assert calls["n"] == 0
    finally:
        app.state.providers = original


async def test_red_stream_sends_the_template_as_a_single_chunk(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    events = await _collect_sse(client, f"/api/v1/conversations/{cid}/messages/stream", {"text": "je veux me tuer"}, h)

    chunks = [e for e in events if e["type"] == "assistant_chunk"]
    assert len(chunks) == 1
    final = next(e for e in events if e["type"] == "assistant_message")
    assert final["decision_level"] == "RED"
    assert final["generation_path"] == "TEMPLATE"
    assert final["provider"] is None


async def test_streamed_reply_is_persisted_and_visible_in_history(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    h = await _patient(client, "acme", "p@acme.example.com")
    cid = (await client.post("/api/v1/conversations", headers=h)).json()["id"]
    await _collect_sse(client, f"/api/v1/conversations/{cid}/messages/stream", {"text": "coucou"}, h)
    items = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()["items"]
    assert [i["author_type"] for i in items] == ["PATIENT", "ASSISTANT"]
