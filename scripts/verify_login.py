#!/usr/bin/env python
"""Verify that an already-provisioned account can actually authenticate.

Companion to provision_user.py: exercises the exact same AuthService code
path the HTTP API uses, but prints which specific check failed (invalid
credentials vs. missing/invalid MFA) instead of the deliberately generic
401 the API returns for both (see backend/app/http.py, account-enumeration
hardening). Useful to confirm a freshly provisioned account works without
guessing from outside over HTTP.

Never prints the password. Computes the current TOTP code itself from the
stored secret so the caller doesn't need an authenticator app for this check.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.db import connect, migrate


def current_totp_code(secret_b32: str) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = int(time.time() // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return str(value).zfill(6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--password-env", required=True, help="Environment variable holding the account's password.")
    parser.add_argument("--totp-secret-env", help="Environment variable holding the base32 TOTP secret, for CLINICIAN/ADMIN accounts.")
    args = parser.parse_args()

    password = os.environ.get(args.password_env)
    if not password:
        parser.error(f"environment variable {args.password_env} is not set")

    totp_code = None
    if args.totp_secret_env:
        secret = os.environ.get(args.totp_secret_env)
        if not secret:
            parser.error(f"environment variable {args.totp_secret_env} is not set")
        totp_code = current_totp_code(secret)

    settings = Settings.from_env()
    conn = connect(settings.database_path)
    migrate(conn)
    try:
        service = AuthService(conn, settings)
        try:
            service.authenticate(args.email, password, "verify-login", totp_code=totp_code)
            print(f"OK: {args.email} authenticated successfully.")
        except PermissionError as error:
            print(f"FAILED: {args.email} could not authenticate: {error}")
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
