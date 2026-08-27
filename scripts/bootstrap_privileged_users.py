#!/usr/bin/env python
"""Idempotently provision CLINICIAN/ADMIN accounts from environment variables
at container startup.

Exists for platforms (e.g. Railway) with no shell access to the running
container's persistent volume after deployment: a pre-deploy/build-time hook
runs in a separate, non-persistent filesystem there, so scripts/provision_user.py
can't be used interactively against the real database the way it can locally
(see docs/deployment/production-readiness.md). This script instead runs as
part of the actual startup command, in the same container and volume as the
app itself.

Safe to run on every container start: skips any role whose account already
exists, and does nothing at all if no PI_BOOTSTRAP_* variable is set. For
each of CLINICIAN and ADMIN, set:

    PI_BOOTSTRAP_<ROLE>_EMAIL
    PI_BOOTSTRAP_<ROLE>_PASSWORD

A TOTP secret is generated and printed once to stdout (never persisted
anywhere but the users table) the first time an account is created.
"""
from __future__ import annotations

import base64
import os
import secrets as pysecrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.db import connect, migrate


def generate_totp_secret() -> str:
    return base64.b32encode(pysecrets.token_bytes(20)).decode("ascii").rstrip("=")


def bootstrap_one(service: AuthService, conn, role: str) -> None:
    email = os.environ.get(f"PI_BOOTSTRAP_{role}_EMAIL")
    password = os.environ.get(f"PI_BOOTSTRAP_{role}_PASSWORD")
    if not email or not password:
        return
    normalized = email.strip().lower()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (normalized,)).fetchone()
    if existing:
        print(f"bootstrap: {role} account {normalized} already exists, skipping.")
        return
    secret = generate_totp_secret()
    user_id = service.provision_privileged_user(email, password, role, secret, "bootstrap")
    print(f"bootstrap: created {role} account {user_id} for {normalized}.")
    print(f"bootstrap: TOTP secret for {normalized} (enter into an authenticator app now, it will not be shown again): {secret}")


def main() -> None:
    settings = Settings.from_env()
    conn = connect(settings.database_path)
    migrate(conn)
    try:
        service = AuthService(conn, settings)
        for role in ("CLINICIAN", "ADMIN"):
            bootstrap_one(service, conn, role)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
