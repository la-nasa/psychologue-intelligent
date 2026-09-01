"""Enrôlement MFA (TOTP, RFC 6238) — Phase 3.

`enroll` génère un secret, le stocke **chiffré**, mais ne l'active pas : la MFA
n'est effective qu'après `activate` (preuve que le patient/clinicien a bien
configuré son application). Les rôles cliniques ne peuvent pas se connecter tant
que la MFA n'est pas active (voir auth_service._MFA_REQUIRED_ROLES).
"""
from __future__ import annotations

import uuid
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError
from app.core.security import new_totp_secret, verify_totp
from app.infrastructure.models import User

_ISSUER = "Psychologue Intelligent"


def _provisioning_uri(secret: str, account: str) -> str:
    label = quote(f"{_ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(_ISSUER)}&digits=6&period=30"


async def enroll(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, request_id: str
) -> dict:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise DomainError("user not found", code="not_found", status_code=404)
    if user.mfa_enabled:
        raise DomainError("multi-factor authentication is already active", code="mfa_already_active", status_code=409)
    secret = new_totp_secret()
    user.mfa_secret_enc = encrypt(secret)
    await audit.record(
        session, request_id=request_id, action="mfa.enroll", resource_type="user",
        resource_id=str(user_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )
    return {"secret": secret, "otpauth_uri": _provisioning_uri(secret, user.email_normalized)}


async def activate(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, code: str, request_id: str
) -> None:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise DomainError("user not found", code="not_found", status_code=404)
    secret = decrypt(user.mfa_secret_enc) if user.mfa_secret_enc else None
    if not secret:
        raise DomainError("start MFA enrolment first", code="mfa_not_enrolled")
    if not verify_totp(secret, code):
        await audit.record(
            session, request_id=request_id, action="mfa.activate", resource_type="user",
            resource_id=str(user_id), organization_id=organization_id, actor_id=user_id, outcome="FAILURE",
        )
        raise DomainError("invalid verification code", code="invalid_code")
    user.mfa_enabled = True
    await audit.record(
        session, request_id=request_id, action="mfa.activate", resource_type="user",
        resource_id=str(user_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )
