from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time


def hash_password(password: str, iterations: int) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("password must contain between 12 and 1024 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_text), int(iteration_text))
        return hmac.compare_digest(digest, base64.b64decode(digest_text))
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def verify_totp(secret_b32: str, code: str, now: int | None = None, window: int = 1) -> bool:
    if not (code.isdigit() and len(code) == 6):
        return False
    instant = int(time.time()) if now is None else now
    try:
        key = base64.b32decode(secret_b32.upper(), casefold=True)
    except (ValueError, TypeError):
        return False
    for offset in range(-window, window + 1):
        counter = (instant // 30) + offset
        if counter < 0:
            continue
        payload = struct.pack(">Q", counter)
        digest = hmac.new(key, payload, hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        value = (struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f"{value:06d}", code):
            return True
    return False
