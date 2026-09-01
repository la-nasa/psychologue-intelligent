from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select


async def _token(client: AsyncClient, slug: str, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": "correct-horse-staple-42"})
    return r.json()["access_token"]


async def test_deletion_request_is_recorded_and_idempotent(client: AsyncClient, make_org) -> None:
    from app.core.db import system_session
    from app.infrastructure.models import DeletionRequest

    await make_org("acme")
    h = {"Authorization": f"Bearer {await _token(client, 'acme', 'p@acme.example.com')}"}

    first = await client.post("/api/v1/privacy/deletion-requests", headers=h)
    second = await client.post("/api/v1/privacy/deletion-requests", headers=h)
    assert first.status_code == second.status_code == 202
    assert first.json()["status"] == "OPEN"

    async with system_session() as session:
        count = (await session.execute(select(func.count()).select_from(DeletionRequest))).scalar_one()
    assert count == 1


async def test_deletion_request_requires_auth(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/privacy/deletion-requests")).status_code == 401
