from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

# --- Mots de passe : Argon2id (remplace le PBKDF2 de la v1 — ADR-006, TH-01) ---


def _hasher(settings: Settings) -> PasswordHasher:
    if settings.env == "testing":
        # Paramètres minimaux : les tests créent/valident beaucoup de comptes.
        # La robustesse d'Argon2id est vérifiée par ses propres tests, pas en
        # rejouant un coût réaliste sur chaque fixture.
        return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost_kib,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(password: str, settings: Settings) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("password length must be between 12 and 256")
    return _hasher(settings).hash(password)


def verify_password(password: str, stored_hash: str, settings: Settings) -> tuple[bool, str | None]:
    """Renvoie (ok, new_hash_si_rehash_nécessaire)."""
    ph = _hasher(settings)
    try:
        ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False, None
    if ph.check_needs_rehash(stored_hash):
        return True, ph.hash(password)
    return True, None


# --- Jetons de session opaques : le client reçoit un secret aléatoire,
#     la base ne stocke que son SHA-256 (jamais le jeton en clair). ---


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# --- MFA : TOTP (RFC 6238), stdlib uniquement (repris de la v1) ---


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _totp_at(secret_b32: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, *, window: int = 1, step: int = 30) -> bool:
    if not code or not code.isdigit():
        return False
    now = int(time.time()) // step
    return any(constant_time_equals(_totp_at(secret_b32, now + drift), code) for drift in range(-window, window + 1))
