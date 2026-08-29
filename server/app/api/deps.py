from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.application import auth_service
from app.core.context import Principal
from app.core.errors import AuthenticationError


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def get_principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise AuthenticationError("bearer token required")
    token = header.removeprefix("Bearer ").strip()
    principal = await auth_service.resolve_principal(token)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
RequestId = Annotated[str, Depends(get_request_id)]
