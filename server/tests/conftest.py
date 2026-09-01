from __future__ import annotations

import os

# Doit être positionné AVANT tout import de `app.*` (l'engine SQLAlchemy est
# construit à l'import de app.core.db et lit ce paramètre pour choisir NullPool).
os.environ["PI_ENV"] = "testing"

import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# La suite exige une vraie base PostgreSQL + Redis (ADR-006 : `docker compose up`
# est le contrat). En local sans les services, `pytest` échoue clairement plutôt
# que de tester à vide.
pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> Iterator[None]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    yield


# Ordre enfant -> parent (respecte les FK). `DELETE` plutôt que `TRUNCATE` :
# sur des tables quasi vides c'est bien plus rapide (pas de verrou exclusif, pas
# de réécriture de fichier, pas de fsync) — la suite passe de ~2s30 à ~5ms par
# test sur ce nettoyage. Aucune séquence à réinitialiser (toutes les PK sont des UUID).
_CLEAN_ORDER = (
    "goal_progress", "goals",
    "memories", "longitudinal_snapshots",
    "clinician_response_reviews",
    "conversation_state", "messages", "conversations",
    "notifications", "notification_channels", "alert_actions", "alerts", "crisis_events", "risk_assessments",
    "patient_clinician_relationships",
    "assessment_reminders", "phq9_assessments",
    "deletion_requests", "communication_preferences", "profiles", "consents",
    "audit_logs", "user_roles", "sessions", "users", "clinics", "organizations",
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    from app.core.db import system_session
    from app.core.redis import get_redis

    # Nettoyage AVANT chaque test => état déterministe même après un run local
    # interrompu. Les tables globales (roles/permissions/consent_versions) sont préservées.
    async with system_session() as session:
        for table in _CLEAN_ORDER:
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608 — noms de tables constants
    # Le rate limiter est distribué (Redis) et partagé : sans ça, les registres
    # de tentatives d'un test épuisent le quota du suivant. Le client est mis en
    # cache pour toute la session (boucle unique) : ne pas le fermer ici.
    await get_redis().flushdb()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_org():
    from app.core.db import system_session
    from app.infrastructure.models import Organization

    async def _make(slug: str | None = None) -> uuid.UUID:
        slug = slug or f"org-{uuid.uuid4().hex[:8]}"
        org_id = uuid.uuid4()
        async with system_session() as session:
            session.add(Organization(id=org_id, name=slug, slug=slug, status="ACTIVE"))
        return org_id

    return _make


@pytest_asyncio.fixture
async def make_user():
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.db import system_session
    from app.core.security import hash_password
    from app.infrastructure.models import Role, User, UserRole

    async def _make(org_id: uuid.UUID, email: str, password: str = "correct-horse-staple-42", roles: tuple[str, ...] = ("PATIENT",)) -> uuid.UUID:
        user_id = uuid.uuid4()
        async with system_session() as session:
            session.add(
                User(
                    id=user_id,
                    organization_id=org_id,
                    email_normalized=email.lower(),
                    password_hash=hash_password(password, get_settings()),
                    status="ACTIVE",
                )
            )
            await session.flush()
            for code in roles:
                role_id = (await session.execute(select(Role.id).where(Role.code == code))).scalar_one()
                session.add(UserRole(id=uuid.uuid4(), organization_id=org_id, user_id=user_id, role_id=role_id))
        return user_id

    return _make
