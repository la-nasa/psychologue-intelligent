from __future__ import annotations

import time
import uuid

import pytest

from app.application import rbac
from app.core.config import get_settings
from app.core.context import Principal
from app.core.crypto import decrypt, encrypt
from app.core.errors import PermissionDeniedError
from app.core.security import (
    _totp_at,
    constant_time_equals,
    hash_password,
    hash_token,
    new_session_token,
    new_totp_secret,
    verify_password,
    verify_totp,
)


def test_password_roundtrip_and_wrong_password() -> None:
    s = get_settings()
    h = hash_password("correct-horse-staple-42", s)
    assert h != "correct-horse-staple-42"
    ok, rehash = verify_password("correct-horse-staple-42", h, s)
    assert ok and rehash is None
    bad, _ = verify_password("not-the-password", h, s)
    assert bad is False


def test_password_length_bounds() -> None:
    s = get_settings()
    with pytest.raises(ValueError):
        hash_password("too-short", s)


def test_token_hash_is_stable_and_opaque() -> None:
    token = new_session_token()
    assert hash_token(token) == hash_token(token)
    assert token not in hash_token(token)
    assert len(hash_token(token)) == 64


def test_constant_time_equals() -> None:
    assert constant_time_equals("abc", "abc")
    assert not constant_time_equals("abc", "abd")


def test_totp_accepts_current_rejects_garbage() -> None:
    secret = new_totp_secret()
    code = _totp_at(secret, int(time.time()) // 30)
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000")
    assert not verify_totp(secret, "not-digits")


def test_field_encryption_roundtrip_and_tamper() -> None:
    ct = encrypt("PHQ-9 item 9 = 2")
    assert ct is not None and ct != "PHQ-9 item 9 = 2"
    assert decrypt(ct) == "PHQ-9 item 9 = 2"
    assert encrypt(None) is None and decrypt(None) is None
    flipped = "A" if ct[12] != "A" else "B"
    with pytest.raises(ValueError):
        decrypt(ct[:12] + flipped + ct[13:])


def test_require_role_denies_patient_clinical_access() -> None:
    patient = Principal(user_id=uuid.uuid4(), organization_id=uuid.uuid4(), email="p@a.example.com", roles=frozenset({"PATIENT"}))
    with pytest.raises(PermissionDeniedError):
        rbac.require_role(patient, "PSYCHOLOGIST", "CLINICAL_SUPERVISOR")
    rbac.require_role(patient, "PATIENT")  # ne lève pas


async def test_permissions_for_roles_resolves_seeded_grants(make_org, make_user) -> None:
    from app.core.db import tenant_session

    org = await make_org()
    await make_user(org, "psy@x.example.com", roles=("PSYCHOLOGIST",))
    async with tenant_session(org) as session:
        perms = await rbac.permissions_for_roles(session, frozenset({"PSYCHOLOGIST"}))
    assert "alert.act" in perms
    assert "admin.users.manage" not in perms
