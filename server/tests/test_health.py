from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_is_always_ok(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "live"}


async def test_readiness_checks_backing_services(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_security_headers_on_every_response(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy", "Referrer-Policy"):
        assert header in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


async def test_unknown_route_is_problem_json(client: AsyncClient) -> None:
    resp = await client.get("/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 404 and "trace_id" in body
