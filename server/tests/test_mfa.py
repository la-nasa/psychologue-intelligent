from __future__ import annotations

import time

from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import encrypt
from app.core.db import system_session
from app.core.security import _totp_at, new_totp_secret
from app.infrastructure.models import User


async def _login(client: AsyncClient, slug: str, email: str, pw: str = "correct-horse-staple-42", totp: str | None = None) -> str:
    body = {"organization_slug": slug, "email": email, "password": pw}
    if totp:
        body["totp_code"] = totp
    r = await client.post("/api/v1/auth/sessions", json=body)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def test_patient_can_enroll_and_activate_mfa(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    token = await _login(client, "acme", "p@acme.example.com")
    h = {"Authorization": f"Bearer {token}"}

    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=h)
    assert enroll.status_code == 201
    secret = enroll.json()["secret"]
    assert enroll.json()["otpauth_uri"].startswith("otpauth://totp/")

    bad = await client.post("/api/v1/auth/mfa/activate", json={"code": "000000"}, headers=h)
    assert bad.status_code == 400

    code = _totp_at(secret, int(time.time()) // 30)
    ok = await client.post("/api/v1/auth/mfa/activate", json={"code": code}, headers=h)
    assert ok.status_code == 204


async def test_enrolling_twice_after_activation_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    token = await _login(client, "acme", "p@acme.example.com")
    h = {"Authorization": f"Bearer {token}"}
    secret = (await client.post("/api/v1/auth/mfa/enroll", headers=h)).json()["secret"]
    await client.post("/api/v1/auth/mfa/activate", json={"code": _totp_at(secret, int(time.time()) // 30)}, headers=h)
    again = await client.post("/api/v1/auth/mfa/enroll", headers=h)
    assert again.status_code == 409


async def test_clinician_enrolls_then_can_log_in_with_totp(client: AsyncClient, make_org, make_user) -> None:
    org_id = await make_org("acme")
    await make_user(org_id, "psy@acme.example.com", roles=("PSYCHOLOGIST",))

    # sans MFA active, le clinicien ne peut pas se connecter du tout
    blocked = await client.post("/api/v1/auth/sessions", json={"organization_slug": "acme", "email": "psy@acme.example.com", "password": "correct-horse-staple-42"})
    assert blocked.status_code == 401

    # ... et il ne peut pas non plus s'enrôler sans jeton (chicken-and-egg). En
    # déploiement, `scripts.bootstrap` pose un premier secret MFA pour les comptes
    # privilégiés. Ici on simule ce provisionnement, puis on vérifie que le login
    # avec TOTP fonctionne.
    secret = new_totp_secret()
    async with system_session() as session:
        user = (await session.execute(select(User).where(User.email_normalized == "psy@acme.example.com"))).scalar_one()
        user.mfa_secret_enc = encrypt(secret)
        user.mfa_enabled = True

    good = await client.post(
        "/api/v1/auth/sessions",
        json={"organization_slug": "acme", "email": "psy@acme.example.com", "password": "correct-horse-staple-42", "totp_code": _totp_at(secret, int(time.time()) // 30)},
    )
    assert good.status_code == 201
    wrong = await client.post(
        "/api/v1/auth/sessions",
        json={"organization_slug": "acme", "email": "psy@acme.example.com", "password": "correct-horse-staple-42", "totp_code": "000000"},
    )
    assert wrong.status_code == 401


async def test_mfa_enroll_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/mfa/enroll")).status_code == 401


async def test_activate_before_enrolling_is_rejected(client: AsyncClient, make_org) -> None:
    await make_org("acme")
    await client.post("/api/v1/auth/register", json={"organization_slug": "acme", "email": "p@acme.example.com", "password": "correct-horse-staple-42"})
    token = await _login(client, "acme", "p@acme.example.com")
    r = await client.post("/api/v1/auth/mfa/activate", json={"code": "123456"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert r.json()["code"] == "mfa_not_enrolled"
