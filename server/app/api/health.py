from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.schemas import StatusResponse
from app.core.db import ping
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=StatusResponse)
async def live() -> StatusResponse:
    # La liveness ne dépend JAMAIS de la base ni de Redis : elle répond
    # "le process est-il vivant", pas "peut-il servir une vraie requête".
    return StatusResponse(status="live")


@router.get("/health/ready", response_model=StatusResponse)
async def ready(response: Response) -> StatusResponse:
    try:
        await ping()
        await get_redis().ping()
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return StatusResponse(status="not-ready")
    return StatusResponse(status="ready")
