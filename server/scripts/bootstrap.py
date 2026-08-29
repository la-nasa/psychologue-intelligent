"""Amorçage idempotent d'une organisation + d'un compte privilégié.

Usage (dans le conteneur api) :
    python -m scripts.bootstrap --org-slug demo --org-name "Clinique de démonstration" \
        --email admin@example.org --password '...' --role ADMIN

Idempotent : relancer ne crée pas de doublon. Ne fait rien sans arguments.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import system_session
from app.core.security import hash_password
from app.infrastructure.models import Organization, Role, User, UserRole


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    async with system_session() as session:
        org = (await session.execute(select(Organization).where(Organization.slug == args.org_slug))).scalar_one_or_none()
        if org is None:
            org = Organization(id=uuid.uuid4(), name=args.org_name, slug=args.org_slug, status="ACTIVE")
            session.add(org)
            await session.flush()
            print(f"created organization {org.slug} ({org.id})")
        else:
            print(f"organization {org.slug} already exists ({org.id})")

        email = args.email.strip().lower()
        user = (
            await session.execute(select(User).where(User.organization_id == org.id, User.email_normalized == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                organization_id=org.id,
                email_normalized=email,
                password_hash=hash_password(args.password, settings),
                status="ACTIVE",
            )
            session.add(user)
            await session.flush()
            print(f"created user {email} ({user.id})")
        else:
            print(f"user {email} already exists ({user.id})")

        role = (await session.execute(select(Role).where(Role.code == args.role))).scalar_one()
        exists = (
            await session.execute(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(UserRole(id=uuid.uuid4(), organization_id=org.id, user_id=user.id, role_id=role.id))
            print(f"granted role {args.role}")
        else:
            print(f"role {args.role} already granted")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-slug", required=True)
    parser.add_argument("--org-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="ADMIN", choices=["ADMIN", "SUPER_ADMIN", "PSYCHOLOGIST"])
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
