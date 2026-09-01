from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, RequestId
from app.application import conversation as orch
from app.core.context import Principal
from app.core.db import tenant_session
from app.core.errors import RateLimitedError
from app.core.redis import rate_limit_allow

router = APIRouter(prefix="/api/v1", tags=["conversation"])


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class ConversationResponse(BaseModel):
    id: str
    status: str


def _deps(request: Request):
    s = request.app.state
    return s.safety, s.risk_model, s.notification_provider, s.providers


async def _rate_limit(principal: Principal) -> None:
    from app.core.config import get_settings

    if not await rate_limit_allow(
        "message", str(principal.user_id), limit=get_settings().rate_limit_message_per_min, window_seconds=60
    ):
        raise RateLimitedError("too many messages")


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def start_conversation(principal: CurrentPrincipal, request_id: RequestId) -> ConversationResponse:
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        convo = await orch.get_or_create_active_conversation(
            session, organization_id=principal.organization_id, patient_id=principal.user_id, request_id=request_id
        )
        return ConversationResponse(id=str(convo.id), status=convo.status)


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: str, body: SendMessageRequest, request: Request, principal: CurrentPrincipal, request_id: RequestId
) -> dict:
    await _rate_limit(principal)
    import uuid

    safety, risk_model, notif, providers = _deps(request)
    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        result = await orch.send_message(
            session, organization_id=principal.organization_id, patient_id=principal.user_id,
            conversation_id=uuid.UUID(conversation_id), text=body.text, safety_config=safety,
            risk_model=risk_model, notification_provider=notif, providers=providers, request_id=request_id,
        )
    return {
        "patient_message": result.patient_message,
        "assistant_message": result.assistant_message,
        "decision_level": result.decision_level,
    }


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str, body: SendMessageRequest, request: Request, principal: CurrentPrincipal, request_id: RequestId
) -> StreamingResponse:
    await _rate_limit(principal)
    import uuid

    safety, risk_model, notif, providers = _deps(request)
    cancel = asyncio.Event()

    async def _watch_disconnect() -> None:
        try:
            while not cancel.is_set():
                if await request.is_disconnected():
                    cancel.set()
                    return
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    async def _events() -> AsyncIterator[str]:
        watcher = asyncio.create_task(_watch_disconnect())
        try:
            async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
                async for event in orch.stream_turn(
                    session, organization_id=principal.organization_id, patient_id=principal.user_id,
                    conversation_id=uuid.UUID(conversation_id), text=body.text, safety_config=safety,
                    risk_model=risk_model, notification_provider=notif, providers=providers,
                    request_id=request_id, cancel=cancel,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            cancel.set()
            watcher.cancel()

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, principal: CurrentPrincipal) -> dict:
    import uuid

    async with tenant_session(principal.organization_id, user_id=principal.user_id) as session:
        items = await orch.get_messages(
            session, patient_id=principal.user_id, conversation_id=uuid.UUID(conversation_id)
        )
    return {"items": items}
