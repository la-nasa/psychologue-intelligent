from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


_settings: Settings = get_settings()

if _settings.env == "testing":
    # pytest-asyncio recrée une boucle d'événements par test ; un pool persistant
    # lierait ses connexions asyncpg à la première boucle ("Event loop is closed").
    engine = create_async_engine(_settings.database_url, poolclass=NullPool, echo=False)
else:
    engine = create_async_engine(
        _settings.database_url,
        pool_size=_settings.db_pool_size,
        max_overflow=_settings.db_max_overflow,
        pool_pre_ping=True,
        echo=False,
    )

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


async def _apply_tenant_guc(session: AsyncSession, organization_id: uuid.UUID | None, user_id: uuid.UUID | None, *, bypass_rls: bool) -> None:
    """Positionne les paramètres de session lus par les politiques RLS (ADR-008).

    ``SET LOCAL`` => portée transaction, réinitialisé automatiquement au commit/rollback,
    donc jamais de fuite d'un contexte de tenant vers la requête suivante sur la même
    connexion du pool.
    """
    # `set_config(name, value, is_local=true)` — équivalent de SET LOCAL mais qui
    # accepte des paramètres liés (SET ne les accepte pas). Portée transaction.
    if bypass_rls:
        await session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        return
    await session.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
    await session.execute(
        text("SELECT set_config('app.current_organization', :org, true)"),
        {"org": str(organization_id) if organization_id is not None else ""},
    )
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id) if user_id is not None else ""},
    )


@asynccontextmanager
async def tenant_session(
    organization_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Session scopée à une organisation. Toute requête métier passe par ici.
    RLS filtre au niveau du moteur PostgreSQL, pas seulement de l'ORM (défense en profondeur)."""
    async with SessionLocal() as session:
        async with session.begin():
            await _apply_tenant_guc(session, organization_id, user_id, bypass_rls=False)
            yield session


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    """Session sans scope de tenant : réservée au bootstrap, aux migrations de données,
    aux tâches plateforme et aux chemins SUPER_ADMIN explicitement audités.
    N'est JAMAIS obtenue depuis un contexte de requête authentifiée ordinaire."""
    async with SessionLocal() as session:
        async with session.begin():
            await _apply_tenant_guc(session, None, None, bypass_rls=True)
            yield session


async def ping() -> None:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
