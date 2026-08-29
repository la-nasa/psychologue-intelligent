from __future__ import annotations

import datetime as dt
import uuid

import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.application import audit
from app.application.rbac import load_roles
from app.core.config import Settings
from app.core.context import Principal
from app.core.crypto import decrypt
from app.core.db import system_session, tenant_session
from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.core.security import (
    constant_time_equals,
    hash_password,
    hash_token,
    verify_password,
    verify_totp,
)
from app.infrastructure.models import Organization, Role, Session, User, UserRole

_MFA_REQUIRED_ROLES = {"PSYCHOLOGIST", "CLINICAL_SUPERVISOR", "ADMIN", "SUPER_ADMIN"}


def _normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if "@" not in email or len(email) > 320:
        raise AuthenticationError("invalid credentials")  # ne pas révéler que c'est l'e-mail
    return email


async def resolve_organization_id(slug: str) -> uuid.UUID:
    async with system_session() as session:
        row = await session.execute(select(Organization.id).where(Organization.slug == slug.strip().lower()))
        org_id = row.scalar_one_or_none()
    if org_id is None:
        raise NotFoundError("organization not found")
    return org_id


async def register_patient(organization_id: uuid.UUID, email: str, password: str, request_id: str) -> uuid.UUID:
    normalized = _normalize_email(email)
    pw_hash = hash_password(password, _settings())
    user_id = uuid.uuid4()
    async with tenant_session(organization_id) as session:
        session.add(
            User(
                id=user_id,
                organization_id=organization_id,
                email_normalized=normalized,
                password_hash=pw_hash,
                status="ACTIVE",
            )
        )
        try:
            await session.flush()
        except IntegrityError:
            # Anti-énumération : même réponse qu'un succès côté API ; on lève un conflit
            # neutre, l'API le traduit en 201 sans divulguer l'existence du compte.
            raise ConflictError("registration could not be completed") from None
        patient_role = await session.execute(select(Role.id).where(Role.code == "PATIENT"))
        session.add(UserRole(id=uuid.uuid4(), organization_id=organization_id, user_id=user_id, role_id=patient_role.scalar_one()))
        await audit.record(
            session,
            request_id=request_id,
            action="user.register",
            resource_type="user",
            resource_id=str(user_id),
            organization_id=organization_id,
            actor_id=user_id,
            outcome="SUCCESS",
        )
    return user_id


async def authenticate(
    organization_id: uuid.UUID,
    email: str,
    password: str,
    request_id: str,
    totp_code: str | None = None,
) -> tuple[str, int]:
    settings = _settings()
    normalized = _normalize_email(email)
    async with tenant_session(organization_id) as session:
        row = await session.execute(
            select(User).where(
                User.organization_id == organization_id,
                User.email_normalized == normalized,
                User.deleted_at.is_(None),
            )
        )
        user = row.scalar_one_or_none()

        ok = False
        rehash: str | None = None
        if user is not None and user.status == "ACTIVE":
            ok, rehash = verify_password(password, user.password_hash, settings)

        if not ok or user is None:
            await audit.record(
                session, request_id=request_id, action="auth.login", resource_type="session",
                organization_id=organization_id, actor_id=user.id if user else None, outcome="FAILURE",
            )
            raise AuthenticationError("invalid credentials")

        roles = await load_roles(session, user.id)
        needs_mfa = user.mfa_enabled or bool(roles & _MFA_REQUIRED_ROLES)
        if needs_mfa:
            secret = decrypt(user.mfa_secret_enc) if user.mfa_secret_enc else None
            if not secret or not totp_code or not verify_totp(secret, totp_code):
                await audit.record(
                    session, request_id=request_id, action="auth.login.mfa", resource_type="session",
                    organization_id=organization_id, actor_id=user.id, outcome="FAILURE",
                )
                raise AuthenticationError("multi-factor authentication required")

        if rehash:
            user.password_hash = rehash

        session_id = uuid.uuid4()
        now = dt.datetime.now(dt.UTC)
        expires_at = now + dt.timedelta(seconds=settings.session_ttl_seconds)
        token = _encode_jwt(
            {"sid": str(session_id), "oid": str(organization_id), "uid": str(user.id), "exp": expires_at},
            settings.jwt_signing_key,
        )
        session.add(
            Session(
                id=session_id,
                organization_id=organization_id,
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=expires_at,
            )
        )
        await audit.record(
            session, request_id=request_id, action="auth.login", resource_type="session",
            resource_id=str(session_id), organization_id=organization_id, actor_id=user.id, outcome="SUCCESS",
        )
    return token, settings.session_ttl_seconds


async def resolve_principal(token: str) -> Principal:
    settings = _settings()
    try:
        claims = jwt.decode(token, settings.jwt_signing_key, algorithms=["HS256"])
        org_id = uuid.UUID(claims["oid"])
        user_id = uuid.UUID(claims["uid"])
        session_id = uuid.UUID(claims["sid"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise AuthenticationError("invalid token") from None

    token_hash = hash_token(token)
    async with tenant_session(org_id) as session:
        row = await session.execute(select(Session).where(Session.id == session_id))
        sess = row.scalar_one_or_none()
        if (
            sess is None
            or not constant_time_equals(sess.token_hash, token_hash)
            or sess.revoked_at is not None
            or sess.expires_at <= dt.datetime.now(dt.UTC)
        ):
            raise AuthenticationError("session is not active")
        user_row = await session.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = user_row.scalar_one_or_none()
        if user is None or user.status != "ACTIVE":
            raise AuthenticationError("account is not active")
        roles = await load_roles(session, user_id)
    return Principal(user_id=user_id, organization_id=org_id, email=user.email_normalized, roles=roles, session_id=session_id)


async def revoke(token: str, request_id: str) -> None:
    settings = _settings()
    try:
        claims = jwt.decode(token, settings.jwt_signing_key, algorithms=["HS256"], options={"verify_exp": False})
        org_id = uuid.UUID(claims["oid"])
        session_id = uuid.UUID(claims["sid"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return
    async with tenant_session(org_id) as session:
        row = await session.execute(select(Session).where(Session.id == session_id))
        sess = row.scalar_one_or_none()
        if sess and sess.revoked_at is None:
            sess.revoked_at = dt.datetime.now(dt.UTC)
            await audit.record(
                session, request_id=request_id, action="auth.logout", resource_type="session",
                resource_id=str(session_id), organization_id=org_id, actor_id=sess.user_id, outcome="SUCCESS",
            )


def _encode_jwt(payload: dict[str, object], key: str) -> str:
    # PyJWT >= 2 renvoie str.
    return jwt.encode(payload, key, algorithm="HS256")


def _settings() -> Settings:
    from app.core.config import get_settings

    return get_settings()
