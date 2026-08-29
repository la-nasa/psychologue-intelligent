from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import LoginRequest, MeResponse, RegisterRequest, StatusResponse, TokenResponse
from app.application import auth_service
from app.core.config import get_settings
from app.core.errors import ConflictError, RateLimitedError
from app.core.redis import rate_limit_allow

router = APIRouter(prefix="/api/v1", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/auth/register", response_model=StatusResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, body: RegisterRequest, request_id: RequestId) -> StatusResponse:
    settings = get_settings()
    if not await rate_limit_allow("register", _client_ip(request), limit=settings.rate_limit_register_per_hour, window_seconds=3600):
        raise RateLimitedError("too many registration attempts")
    org_id = await auth_service.resolve_organization_id(body.organization_slug)
    try:
        await auth_service.register_patient(org_id, body.email, body.password.get_secret_value(), request_id)
    except ConflictError:
        # Anti-énumération de comptes : réponse identique à un succès.
        pass
    return StatusResponse(status="created")


@router.post("/auth/sessions", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: Request, body: LoginRequest, request_id: RequestId) -> TokenResponse:
    settings = get_settings()
    key = f"{_client_ip(request)}:{body.organization_slug}:{body.email.lower()}"
    if not await rate_limit_allow("login", key, limit=settings.rate_limit_login_per_15min, window_seconds=900):
        raise RateLimitedError("too many attempts")
    org_id = await auth_service.resolve_organization_id(body.organization_slug)
    token, expires_in = await auth_service.authenticate(
        org_id, body.email, body.password.get_secret_value(), request_id, body.totp_code
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, request_id: RequestId, _: CurrentPrincipal) -> Response:
    header = request.headers.get("authorization", "")
    await auth_service.revoke(header.removeprefix("Bearer ").strip(), request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        id=str(principal.user_id),
        email=principal.email,
        organization_id=str(principal.organization_id),
        roles=sorted(principal.roles),
    )
