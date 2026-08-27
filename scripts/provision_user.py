#!/usr/bin/env python
"""Provision a CLINICIAN or ADMIN account.

Run locally by an operator who has already verified the person's identity and
role. There is no self-registration path for these roles: see
backend/app/auth.py::provision_privileged_user for why.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import secrets
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.auth import AuthService
from backend.app.config import Settings
from backend.app.db import connect, migrate


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("role", choices=["CLINICIAN", "ADMIN"])
    args = parser.parse_args()

    password = getpass.getpass("Temporary password (12-1024 characters, share it out of band): ")
    settings = Settings.from_env()
    conn = connect(settings.database_path)
    migrate(conn)
    try:
        secret = generate_totp_secret()
        user_id = AuthService(conn, settings).provision_privileged_user(
            args.email, password, args.role, secret, f"provision-{uuid4()}"
        )
    finally:
        conn.close()

    print(f"Created {args.role} account {user_id} for {args.email}.")
    print(f"TOTP secret (enter into an authenticator app now, it will not be shown again): {secret}")


if __name__ == "__main__":
    main()
