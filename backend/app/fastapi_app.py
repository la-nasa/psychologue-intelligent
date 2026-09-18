from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from .auth import AuthService
from .config import Settings
from .conversation import get_messages, get_or_create_active_conversation, stream_message
from .db import connect, migrate
from .model_router import build_model_router
from .notifications import LogNotificationProvider
from .policy import load_crisis_policy, load_crisis_rules, load_response_templates
from .ai import KeywordRiskModel, TemplatedSupportiveResponder

LOGGER = logging.getLogger("psychologue_intelligent.fastapi")


def create_app(settings: Settings | None = None):
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError("install the realtime extra: pip install -e '.[realtime]'") from exc

    settings = settings or Settings.from_env()
    bootstrap = connect(settings.database_path)
    migrate(bootstrap)
    bootstrap.close()
    policy = load_crisis_policy(settings.crisis_policy_path)
    rules = load_crisis_rules(settings.crisis_rules_path)
    templates = load_response_templates(settings.response_templates_path)
    fallback = TemplatedSupportiveResponder(templates.green_acknowledgments)
    router = build_model_router(settings, fallback)
    risk_model = KeywordRiskModel()
    notifications = LogNotificationProvider()

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(title="Psychologue Intelligent realtime API", version="1", lifespan=lifespan)

    @app.get("/health/live")
    async def live():
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready():
        conn = connect(settings.database_path)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return {"status": "ready"}

    def authenticated_user(token: str | None):
        if not token:
            return None
        conn = connect(settings.database_path)
        try:
            return AuthService(conn, settings).current_user(token, "realtime")
        except (ValueError, PermissionError):
            return None
        finally:
            conn.close()

    @app.websocket("/ws/conversations/{conversation_id}")
    async def conversation_socket(websocket: WebSocket, conversation_id: str):
        token = websocket.headers.get("authorization", "").removeprefix("Bearer ") or websocket.query_params.get("token")
        user = authenticated_user(token)
        if not user:
            await websocket.close(code=4401, reason="authentication required")
            return
        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_json()
                text = payload.get("text") if isinstance(payload, dict) else None
                if not isinstance(text, str) or not text.strip():
                    await websocket.send_json({"type": "error", "code": "INVALID_MESSAGE"})
                    continue
                await websocket.send_json({"type": "started"})
                conn = connect(settings.database_path)
                try:
                    chunks, result = await _stream_in_thread(conn, user["id"], conversation_id, text, risk_model, policy, rules, templates, router, notifications, settings)
                    for chunk in chunks:
                        await websocket.send_json({"type": "token", "text": chunk})
                    await websocket.send_json({"type": "completed", "message": result})
                except PermissionError:
                    await websocket.send_json({"type": "error", "code": "FORBIDDEN"})
                except ValueError:
                    await websocket.send_json({"type": "error", "code": "INVALID_MESSAGE"})
                except Exception:
                    LOGGER.exception("websocket conversation failed")
                    await websocket.send_json({"type": "error", "code": "STREAM_FAILED"})
                finally:
                    conn.close()
        except WebSocketDisconnect:
            return

    @app.get("/api/v1/conversations/{conversation_id}/messages")
    async def messages(conversation_id: str, token: str | None = None):
        user = authenticated_user(token)
        if not user:
            return JSONResponse({"error": "authentication required"}, status_code=401)
        conn = connect(settings.database_path)
        try:
            return {"items": get_messages(conn, user["id"], conversation_id)}
        finally:
            conn.close()

    return app


async def _stream_in_thread(conn, patient_id, conversation_id, text, risk_model, policy, rules, templates, router, notifications, settings):
    result = await asyncio.to_thread(
        lambda: list(stream_message(conn, patient_id, conversation_id, text, risk_model, policy, rules, templates, router, notifications, "websocket", settings))
    )
    final = result[-1]
    return result[:-1], final
