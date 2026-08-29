from __future__ import annotations

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, slug: str, email: str, password: str = "correct-horse-staple-42") -> str:
    r = await client.post("/api/v1/auth/register", json={"organization_slug": slug, "email": email, "password": password})
    assert r.status_code == 201
    r = await client.post(
        "/api/v1/auth/sessions", json={"organization_slug": slug, "email": email, "password": password}
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def test_register_then_login_then_me(client: AsyncClient, make_org) -> None:
    org_id = await make_org("acme")
    token = await _register_and_login(client, "acme", "p1@acme.example.com")
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "p1@acme.example.com"
    assert body["organization_id"] == str(org_id)
    assert body["roles"] == ["PATIENT"]


async def test_wrong_password_is_generic_401(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "wrong-but-long-enough"})
    assert r.status_code == 401
    assert r.json()["code"] == "authentication_failed"


async def test_unknown_email_and_wrong_password_are_indistinguishable(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    a = await client.post("/api/v1/auth/sessions", json={"organization_slug": "acme", "email": "ghost@acme.example.com", "password": "whatever-long-enough"})
    assert a.status_code == 401
    assert a.json()["title"] == "invalid credentials"


async def test_registration_does_not_leak_account_existence(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    first = await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "dup@acme.example.com", "password": "correct-horse-staple-42"})
    second = await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "dup@acme.example.com", "password": "correct-horse-staple-42"})
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()


async def test_revoked_session_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    token = await _register_and_login(client, "acme", "p@acme.example.com")
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 401


async def test_tampered_token_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    token = await _register_and_login(client, "acme", "p@acme.example.com")
    r = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}x"})
    assert r.status_code == 401


async def test_missing_bearer_is_rejected(client: AsyncClient) -> None:
    r = await client.get("/api/v1/me")
    assert r.status_code == 401


async def test_login_response_never_sets_a_cookie(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    r = await client.post("/api/v1/auth/sessions", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    assert "set-cookie" not in {k.lower() for k in r.headers}


async def test_role_field_in_body_is_ignored(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    r = await client.post(
        "/api/v1/auth/register",
        json={"organization_slug": "acme", "email": "sneaky@acme.example.com", "password": "correct-horse-staple-42", "role": "ADMIN", "roles": ["ADMIN"]},
    )
    assert r.status_code == 201
    login = await client.post("/api/v1/auth/sessions", json={"organization_slug": "acme", "email": "sneaky@acme.example.com", "password": "correct-horse-staple-42"})
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["roles"] == ["PATIENT"]


async def test_unknown_organization_is_404(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"organization_slug": "does-not-exist", "email": "p@x.example.com", "password": "correct-horse-staple-42"},
    )
    assert r.status_code == 404


async def test_clinician_login_requires_totp(client: AsyncClient, make_org, make_user) -> None:
    org_id = await make_org("acme")
    await make_user(org_id, "psy@acme.example.com", roles=("PSYCHOLOGIST",))
    r = await client.post(
        "/api/v1/auth/sessions",
        json={"organization_slug": "acme", "email": "psy@acme.example.com", "password": "correct-horse-staple-42"},
    )
    assert r.status_code == 401
    assert "multi-factor" in r.json()["title"]
