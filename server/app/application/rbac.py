from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import Principal
from app.core.errors import PermissionDeniedError
from app.infrastructure.models import Permission, Role, RolePermission, UserRole


async def load_roles(session: AsyncSession, user_id: uuid.UUID) -> frozenset[str]:
    rows = await session.execute(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    )
    return frozenset(rows.scalars().all())


async def permissions_for_roles(session: AsyncSession, roles: frozenset[str]) -> frozenset[str]:
    if not roles:
        return frozenset()
    rows = await session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.code.in_(roles))
    )
    return frozenset(rows.scalars().all())


def require_role(principal: Principal, *roles: str) -> None:
    """Vérification côté serveur, deny-by-default (overview-v2 §15 invariant 3).
    `PATIENT` ne peut jamais satisfaire une exigence de rôle clinique."""
    if not principal.has_role(*roles):
        raise PermissionDeniedError("insufficient role")


async def require_permission(session: AsyncSession, principal: Principal, permission: str) -> None:
    granted = await permissions_for_roles(session, principal.roles)
    if permission not in granted:
        raise PermissionDeniedError("insufficient permission")
