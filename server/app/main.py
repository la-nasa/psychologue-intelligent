from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, assessment, auth, conversation, goals, health
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.observability import configure_tracing, instrument_app
from app.core.redis import close_redis

# En-têtes de sécurité sur TOUTES les réponses (repris de v1 SEC-002).
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=(), usb=()",
    "Cache-Control": "no-store",
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json_output=settings.env != "development", level="INFO")
    configure_tracing(settings)

    app = FastAPI(
        title="Psychologue Intelligent V2 — API",
        version="0.2.0",
        description="Monolithe modulaire. Voir docs/architecture/overview-v2.md.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,  # jeton Bearer explicite, jamais de cookie (v1 TH-12)
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["authorization", "content-type", "x-request-id"],
    )

    @app.middleware("http")
    async def context_and_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path, method=request.method)
        started = time.perf_counter()
        log = get_logger("pi.access")
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_failed", duration_ms=round((time.perf_counter() - started) * 1000, 1))
            raise
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "path", "method")
        response.headers.setdefault("X-Request-ID", request_id)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        log.info(
            "request_completed",
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response

    # Chargées une fois au démarrage : une politique invalide ou non approuvée
    # (hors development) fait échouer le boot, jamais une requête (ADR-002/004).
    from app.ai.providers.external import ExternalLLMProvider
    from app.ai.providers.keyword_risk import KeywordRiskModel
    from app.ai.providers.local import LocalSupportiveResponder
    from app.ai.routing.model_router import Providers
    from app.application.notifications import LogNotificationProvider
    from app.application.safety import load_safety_config

    app.state.safety = load_safety_config(settings)
    app.state.risk_model = KeywordRiskModel()
    app.state.notification_provider = LogNotificationProvider()
    app.state.providers = Providers(local=LocalSupportiveResponder(), external=ExternalLLMProvider())

    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(account.router)
    app.include_router(conversation.router)
    app.include_router(goals.router)
    app.include_router(assessment.router)

    if settings.otel_enabled and settings.env != "testing":
        instrument_app(app)

    return app


app = create_app()
