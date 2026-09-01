from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentPrincipal, RequestId
from app.api.schemas import (
    ConsentItem,
    ConsentRequest,
    PreferencesResponse,
    PreferencesUpdateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    StatusResponse,
)
from app.application import account, consent, profile
from app.core.db import tenant_session

router = APIRouter(prefix="/api/v1", tags=["account"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(principal: CurrentPrincipal) -> ProfileResponse:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return ProfileResponse(**await profile.get_profile(session, principal.user_id))


@router.post("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def save_profile(body: ProfileUpdateRequest, principal: CurrentPrincipal, request_id: RequestId) -> Response:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await profile.save_profile(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            display_name=body.display_name, about_me=body.about_me, language=body.language, request_id=request_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/profile/preferences", response_model=PreferencesResponse)
async def get_preferences(principal: CurrentPrincipal) -> PreferencesResponse:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return PreferencesResponse(**await profile.get_preferences(session, principal.user_id))


@router.put("/profile/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def save_preferences(
    body: PreferencesUpdateRequest, principal: CurrentPrincipal, request_id: RequestId
) -> Response:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await profile.save_preferences(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            tone=body.tone, response_length=body.response_length,
            question_frequency=body.question_frequency, directiveness=body.directiveness, request_id=request_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/consents", response_model=dict[str, list[ConsentItem]])
async def list_consents(principal: CurrentPrincipal) -> dict:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        return {"items": await consent.list_for_user(session, principal.user_id)}


@router.post("/consents", status_code=status.HTTP_204_NO_CONTENT)
async def grant_consent(body: ConsentRequest, principal: CurrentPrincipal, request_id: RequestId) -> Response:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await consent.grant(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            purpose=body.purpose, request_id=request_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/consents/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_consent(body: ConsentRequest, principal: CurrentPrincipal, request_id: RequestId) -> Response:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        await consent.revoke(
            session, organization_id=principal.organization_id, user_id=principal.user_id,
            purpose=body.purpose, request_id=request_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/privacy/deletion-requests", response_model=StatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_deletion(principal: CurrentPrincipal, request_id: RequestId) -> StatusResponse:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        result = await account.request_deletion(
            session, organization_id=principal.organization_id, user_id=principal.user_id, request_id=request_id
        )
    return StatusResponse(status=result)
