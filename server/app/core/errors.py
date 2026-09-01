from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CONTENT_TYPE_PROBLEM = "application/problem+json"


class DomainError(Exception):
    """Erreur métier attendue. Jamais une trace, jamais un détail interne exposé."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "domain_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class PermissionDeniedError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


class AuthenticationError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_failed"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitedError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


def _problem(request: Request, *, status_code: int, code: str, title: str, extra: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"about:blank#{code}",
        "title": title,
        "status": status_code,
        "code": code,
        "trace_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type=CONTENT_TYPE_PROBLEM)


def install_exception_handlers(app: Any) -> None:
    """RFC 9457. Aucune réponse n'expose de stack trace, de SQL ou de chemin interne
    (threat-model-v2 hérite de v1 TH-09 / SEC-002)."""

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(request, status_code=exc.status_code, code=exc.code, title=exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # On expose les emplacements de champ (utile au client) mais jamais les valeurs reçues.
        fields = [".".join(str(p) for p in err["loc"]) for err in exc.errors()]
        return _problem(
            request,
            status_code=422,
            code="validation_error",
            title="request validation failed",
            extra={"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(request, status_code=exc.status_code, code="http_error", title=str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Le détail réel est journalisé (avec request_id) par le middleware, jamais renvoyé.
        return _problem(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            title="internal error",
        )
