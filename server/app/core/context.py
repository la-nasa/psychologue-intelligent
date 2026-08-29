from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """L'utilisateur authentifié courant, dérivé du jeton — jamais du corps de requête."""

    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    roles: frozenset[str] = field(default_factory=frozenset)
    session_id: uuid.UUID | None = None

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    @property
    def is_super_admin(self) -> bool:
        return "SUPER_ADMIN" in self.roles


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    principal: Principal | None = None
