from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from urllib.parse import parse_qs
from uuid import uuid4

from . import admin, clinician, conversation, learning
from .ai import KeywordRiskModel, LLMProvider, TemplatedSupportiveResponder
from .auth import AuthService, require_role
from .config import Settings
from .db import connect, migrate
from .emotion import TfidfLogisticEmotionModel
from .local_llm import LocalGenerativeResponder
from .notifications import LogNotificationProvider
from .policy import load_crisis_policy, load_crisis_rules, load_response_templates

LOGGER = logging.getLogger("psychologue_intelligent")
MAX_BODY_BYTES = 16_384


def match_path(template: str, path: str) -> dict[str, str] | None:
    template_parts, path_parts = template.strip("/").split("/"), path.strip("/").split("/")
    if len(template_parts) != len(path_parts):
        return None
    params: dict[str, str] = {}
    for template_part, path_part in zip(template_parts, path_parts, strict=True):
        if template_part.startswith("{") and template_part.endswith("}"):
            params[template_part[1:-1]] = path_part
        elif template_part != path_part:
            return None
    return params


class RateLimiter:
    """Generic sliding-window limiter, keyed by whatever the caller chooses
    (IP for anonymous endpoints, user id for authenticated ones) -- used for
    login, registration, and message sending, not just login."""

    def __init__(self, limit: int = 5, window_seconds: int = 900):
        self.limit, self.window = limit, window_seconds
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        now, values = time.monotonic(), self.attempts[key]
        while values and values[0] <= now - self.window:
            values.popleft()
        if len(values) >= self.limit:
            return False
        values.append(now)
        return True


def application(settings: Settings) -> Callable:
    # A single shared sqlite3.Connection here would be a serious latent bug: by
    # default (check_same_thread=True) it can only be used by the thread that
    # created it. wsgiref's default single-threaded server never triggers it,
    # but any threaded WSGI server (gunicorn --threads, waitress, a threading
    # mixin) would 500 on almost every request except by luck of which thread
    # handled it -- found and reproduced while exercising this exact scenario
    # (Phase 11-12 hardening). Opening one connection per request sidesteps the
    # thread-affinity question entirely; WAL mode is designed for concurrent
    # readers plus one writer across separate connections.
    bootstrap_conn = connect(settings.database_path)
    try:
        migrate(bootstrap_conn)
    finally:
        bootstrap_conn.close()

    limiter = RateLimiter()
    registration_limiter = RateLimiter(limit=10, window_seconds=3600)
    message_limiter = RateLimiter(limit=30, window_seconds=60)
    phq9_limiter = RateLimiter(limit=20, window_seconds=3600)

    # Loaded once at startup so an invalid or unapproved policy fails fast at
    # boot, never mid-request. See ADR-002/ADR-004: these are data, not code.
    crisis_policy = load_crisis_policy(settings.crisis_policy_path)
    crisis_rules = load_crisis_rules(settings.crisis_rules_path)
    response_templates = load_response_templates(settings.response_templates_path)
    risk_model = KeywordRiskModel()
    templated_responder = TemplatedSupportiveResponder(response_templates.green_acknowledgments)
    if settings.responder_mode == "local-llm":
        # ADR-005: a self-hosted generative model, GREEN-level replies only --
        # ORANGE/RED are structurally unreachable from it (see responder.py).
        # templated_responder is its fail-safe fallback, not a separate mode:
        # any load or generation failure degrades to the fixed acknowledgment
        # rather than ever losing a reply or crashing the request.
        llm: LLMProvider = LocalGenerativeResponder(
            settings.llm_model_path, fallback=templated_responder,
            max_reply_tokens=settings.llm_max_reply_tokens, context_tokens=settings.llm_context_tokens,
        )
    else:
        llm = templated_responder
    notification_provider = LogNotificationProvider()
    try:
        emotion_model = TfidfLogisticEmotionModel(settings.emotion_model_path)
    except (OSError, ValueError, KeyError):
        # Observability-only: if the trained artifact isn't present (e.g. the
        # training script hasn't been run in this environment), the app must
        # still start and the crisis pipeline must still work without it.
        LOGGER.warning("emotion model artifact unavailable at %s; running without it", settings.emotion_model_path)
        emotion_model = None

    def app(environ: dict, start_response: Callable):
        request_id = environ.get("HTTP_X_REQUEST_ID") or str(uuid4())
        headers = [
            ("Content-Type", "application/problem+json"),
            ("X-Request-ID", request_id),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            # SEC-002 (security audit, Phase 14+): this is a pure JSON API -- it
            # never renders anything a browser would execute -- so the strictest
            # possible CSP (deny everything) is correct here, not a compromise.
            ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
            # Harmless to send over plain HTTP in development (browsers ignore it
            # outside HTTPS) and required once this sits behind TLS in production.
            ("Strict-Transport-Security", "max-age=63072000; includeSubDomains"),
            ("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=(), usb=()"),
        ]

        def respond(status: str, body: dict, content_type: str = "application/json"):
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            safe_headers = [(name, value) for name, value in headers if name != "Content-Type"]
            start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(payload))), *safe_headers])
            return [payload]

        def problem(status: str, title: str):
            return respond(status, {"type": "about:blank", "title": title, "status": int(status[:3]), "trace_id": request_id}, "application/problem+json")

        method, path = environ.get("REQUEST_METHOD", ""), environ.get("PATH_INFO", "")
        conn = None
        try:
            if method == "GET" and path == "/health/live":
                # Liveness must never depend on the database: it answers "is the
                # process itself responsive", not "can it serve real requests".
                return respond("200 OK", {"status": "live"})
            conn = connect(settings.database_path)
            if method == "GET" and path == "/health/ready":
                conn.execute("SELECT 1").fetchone()
                return respond("200 OK", {"status": "ready"})
            if method not in {"POST", "GET"}:
                return problem("405 Method Not Allowed", "method not allowed")
            if method == "POST":
                if environ.get("CONTENT_TYPE", "").split(";", 1)[0] != "application/json":
                    return problem("415 Unsupported Media Type", "application/json required")
                length = int(environ.get("CONTENT_LENGTH") or "0")
                if length < 0 or length > MAX_BODY_BYTES:
                    return problem("413 Payload Too Large", "invalid payload size")
                if length == 0:
                    data = {}
                else:
                    try:
                        data = json.loads(environ["wsgi.input"].read(length))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        return problem("400 Bad Request", "invalid json")
            else:
                data = {}
            service = AuthService(conn, settings)
            if method == "POST" and path == "/api/v1/auth/register":
                if not registration_limiter.allowed(environ.get("REMOTE_ADDR", "")):
                    return problem("429 Too Many Requests", "too many attempts")
                service.register_patient(str(data.get("email", "")), str(data.get("password", "")), request_id)
                return respond("201 Created", {"status": "created"})
            if method == "POST" and path == "/api/v1/auth/sessions":
                key = f"{environ.get('REMOTE_ADDR','')}:{str(data.get('email','')).lower()}"
                if not limiter.allowed(key):
                    return problem("429 Too Many Requests", "too many attempts")
                token = service.authenticate(str(data.get("email", "")), str(data.get("password", "")), request_id, data.get("totp_code"))
                return respond("201 Created", {"access_token": token, "token_type": "Bearer", "expires_in": settings.session_ttl_seconds})  # nosec B105 -- "Bearer" is an auth scheme name, not a password
            authorization = environ.get("HTTP_AUTHORIZATION", "")
            if not authorization.startswith("Bearer "):
                return problem("401 Unauthorized", "bearer token required")
            token = authorization.removeprefix("Bearer ")
            user = service.current_user(token, request_id)
            if method == "GET" and path == "/api/v1/me":
                return respond("200 OK", {"id": user["id"], "email": user["email"], "role": user["role"]})
            if method == "POST" and path == "/api/v1/profile":
                service.save_profile(user["id"], str(data.get("display_name", "")), request_id)
                return respond("204 No Content", {})
            if method == "POST" and path == "/api/v1/consents":
                service.grant_consent(user["id"], str(data.get("purpose", "")), str(data.get("version", "")), request_id)
                return respond("204 No Content", {})
            if method == "POST" and path == "/api/v1/consents/revoke":
                service.revoke_consent(user["id"], str(data.get("purpose", "")), request_id)
                return respond("204 No Content", {})
            if method == "POST" and path == "/api/v1/privacy/deletion-requests":
                service.request_deletion(user["id"], request_id)
                return respond("202 Accepted", {"status": "open"})
            if method == "POST" and path == "/api/v1/assessments/phq9":
                # SEC-003 (security audit, Phase 14+): this write endpoint had no
                # rate limit at all, unlike the adjacent message-sending endpoint --
                # an inconsistency, not a deliberate choice. 20/hour is generous for
                # a clinical instrument nobody legitimately fills out that often.
                if not phq9_limiter.allowed(user["id"]):
                    return problem("429 Too Many Requests", "too many assessments submitted")
                answers = data.get("answers")
                if not isinstance(answers, list):
                    raise ValueError("answers must be a list")
                return respond("201 Created", service.submit_phq9(user["id"], answers, request_id))
            if method == "GET" and path == "/api/v1/assessments/phq9":
                return respond("200 OK", {"items": service.phq9_history(user["id"])})
            if method == "POST" and path == "/api/v1/auth/logout":
                service.revoke(token, request_id)
                return respond("204 No Content", {}, "application/json")
            if method == "POST" and path == "/api/v1/conversations":
                convo = conversation.get_or_create_active_conversation(conn, user["id"], request_id)
                return respond("201 Created", {"id": convo["id"], "status": convo["status"]})
            params = match_path("/api/v1/conversations/{id}/messages", path)
            if method == "POST" and params is not None:
                if not message_limiter.allowed(user["id"]):
                    return problem("429 Too Many Requests", "too many messages")
                result = conversation.send_message(
                    conn, user["id"], params["id"], str(data.get("text", "")),
                    risk_model, crisis_policy, crisis_rules, response_templates, llm, notification_provider, request_id,
                    emotion_model=emotion_model,
                )
                return respond("201 Created", result)
            if method == "GET" and params is not None:
                return respond("200 OK", {"items": conversation.get_messages(conn, user["id"], params["id"])})
            if method == "POST" and path == "/api/v1/admin/relationships":
                require_role(user, "ADMIN")
                relationship_id = clinician.create_relationship(conn, str(data.get("patient_id", "")), str(data.get("clinician_id", "")), user["id"], request_id)
                return respond("201 Created", {"id": relationship_id})
            params = match_path("/api/v1/admin/relationships/{id}/end", path)
            if method == "POST" and params is not None:
                require_role(user, "ADMIN")
                clinician.end_relationship(conn, params["id"], user["id"], request_id)
                return respond("204 No Content", {})
            if method == "GET" and path == "/api/v1/admin/relationships":
                require_role(user, "ADMIN")
                query = parse_qs(environ.get("QUERY_STRING", ""))
                return respond("200 OK", {"items": admin.list_relationships(conn, query.get("status", [None])[0])})
            if method == "GET" and path == "/api/v1/admin/users":
                require_role(user, "ADMIN")
                query = parse_qs(environ.get("QUERY_STRING", ""))
                return respond("200 OK", {"items": admin.list_users(conn, query.get("role", [None])[0])})
            if method == "GET" and path == "/api/v1/clinician/patients":
                require_role(user, "CLINICIAN")
                return respond("200 OK", {"items": clinician.list_patients_for_clinician(conn, user["id"])})
            params = match_path("/api/v1/clinician/patients/{id}/timeline", path)
            if method == "GET" and params is not None:
                require_role(user, "CLINICIAN")
                return respond("200 OK", clinician.patient_timeline(conn, user["id"], params["id"]))
            if method == "GET" and path == "/api/v1/clinician/alerts":
                require_role(user, "CLINICIAN")
                query = parse_qs(environ.get("QUERY_STRING", ""))
                level = query.get("level", [None])[0]
                status_filter = query.get("status", [None])[0]
                return respond("200 OK", {"items": clinician.list_alerts_for_clinician(conn, user["id"], level, status_filter)})
            params = match_path("/api/v1/clinician/alerts/{id}/actions", path)
            if method == "POST" and params is not None:
                require_role(user, "CLINICIAN")
                updated = clinician.act_on_alert(conn, user["id"], params["id"], str(data.get("action", "")), str(data.get("justification", "")), request_id)
                return respond("200 OK", {"id": updated["id"], "status": updated["status"]})
            if method == "POST" and path == "/api/v1/admin/learning/sample":
                require_role(user, "ADMIN")
                created = learning.sample_and_queue_for_review(conn, user["id"], request_id)
                return respond("201 Created", {"created": len(created)})
            if method == "GET" and path == "/api/v1/clinician/learning/feedback":
                require_role(user, "CLINICIAN")
                return respond("200 OK", {"items": learning.list_pending_feedback(conn)})
            params = match_path("/api/v1/clinician/learning/feedback/{id}/review", path)
            if method == "POST" and params is not None:
                require_role(user, "CLINICIAN")
                updated = learning.review_feedback(conn, params["id"], user["id"], str(data.get("decision", "")), str(data.get("justification", "")), request_id)
                return respond("200 OK", {"id": updated["id"], "review_status": updated["review_status"]})
            if method == "POST" and path == "/api/v1/admin/learning/datasets":
                require_role(user, "ADMIN")
                return respond("201 Created", learning.create_dataset_version(conn, user["id"], request_id))
            if method == "GET" and path == "/api/v1/admin/learning/datasets":
                require_role(user, "ADMIN")
                return respond("200 OK", {"items": learning.list_datasets(conn)})
            if method == "POST" and path == "/api/v1/admin/learning/models":
                require_role(user, "ADMIN")
                registered_model = learning.register_model_version(
                    conn, user["id"], str(data.get("kind", "")), str(data.get("version", "")),
                    data.get("dataset_id"), data.get("metrics") or {}, request_id,
                )
                return respond("201 Created", registered_model)
            if method == "GET" and path == "/api/v1/admin/learning/models":
                require_role(user, "ADMIN")
                return respond("200 OK", {"items": learning.list_model_versions(conn)})
            if method == "GET" and path == "/api/v1/clinician/learning/models":
                # Clinicians need visibility into pending model versions to cast
                # their (dual-approval) decision -- no patient data is in this list.
                require_role(user, "CLINICIAN")
                return respond("200 OK", {"items": learning.list_model_versions(conn)})
            params = match_path("/api/v1/clinician/learning/models/{id}/decisions", path)
            if method == "POST" and params is not None:
                require_role(user, "CLINICIAN")
                updated = learning.decide_model_version(conn, params["id"], user["id"], str(data.get("decision", "")), str(data.get("justification", "")), request_id)
                return respond("200 OK", {"id": updated["id"], "status": updated["status"]})
            params = match_path("/api/v1/admin/learning/models/{id}/deploy", path)
            if method == "POST" and params is not None:
                require_role(user, "ADMIN")
                updated = learning.deploy_model_version(conn, params["id"], user["id"], request_id)
                return respond("200 OK", {"id": updated["id"], "status": updated["status"]})
            params = match_path("/api/v1/admin/learning/models/{id}/rollback", path)
            if method == "POST" and params is not None:
                require_role(user, "ADMIN")
                updated = learning.rollback_model_version(conn, params["id"], user["id"], request_id)
                return respond("200 OK", {"id": updated["id"], "status": updated["status"]})
            return problem("404 Not Found", "not found")
        except (ValueError, PermissionError) as error:
            LOGGER.info("request rejected request_id=%s reason=%s", request_id, str(error))
            return problem("401 Unauthorized", "request rejected")
        except Exception:
            LOGGER.exception("request failure request_id=%s", request_id)
            return problem("500 Internal Server Error", "internal error")
        finally:
            if conn is not None:
                conn.close()

    # No persistent connection to close anymore (see comment above): kept as a
    # no-op so existing callers (every test's tearDown) don't need to change.
    app.close = lambda: None  # type: ignore[attr-defined]
    return app
