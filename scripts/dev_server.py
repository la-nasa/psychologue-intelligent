#!/usr/bin/env python
"""Local development server only: serves the patient and clinician static
frontends alongside the API on one origin, so browser-relative fetches work
without CORS. This is not a production static file server (no caching
headers, no compression, no TLS) and must never be used as one."""
from __future__ import annotations

import mimetypes
import sys
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.http import application as api_application

FRONTEND_ROOT = (Path(__file__).resolve().parents[1] / "frontend").resolve()


def _safe_static_path(relative: str) -> Path | None:
    candidate = (FRONTEND_ROOT / relative).resolve()
    if not candidate.is_relative_to(FRONTEND_ROOT):
        return None
    return candidate


# SEC-002 (security audit, Phase 14+): none of the three frontends use inline
# scripts/handlers or any external script/style host (verified by grep across
# all three index.html files), so this CSP is not a loosened compromise.
_STATIC_SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"),
    ("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=(), usb=()"),
]


def _serve_static(relative: str, start_response):
    path = _safe_static_path(relative)
    if path is None or not path.is_file():
        start_response("404 Not Found", [("Content-Type", "text/plain"), *_STATIC_SECURITY_HEADERS])
        return [b"not found"]
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    data = path.read_bytes()
    start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(data))), *_STATIC_SECURITY_HEADERS])
    return [data]


def make_dev_app(settings: Settings):
    api_app = api_application(settings)

    def app(environ, start_response):
        path_info = environ.get("PATH_INFO", "/")
        if path_info.startswith(("/api/", "/health/")):
            return api_app(environ, start_response)
        for section in ("clinician", "admin"):
            if path_info == f"/{section}" or path_info.startswith(f"/{section}/"):
                relative = path_info[len(f"/{section}"):].lstrip("/") or "index.html"
                return _serve_static(f"{section}/{relative}", start_response)
        relative = path_info.lstrip("/") or "index.html"
        return _serve_static(relative, start_response)

    app.close = api_app.close  # type: ignore[attr-defined]
    return app


if __name__ == "__main__":
    settings = Settings.from_env()
    with make_server("127.0.0.1", 8000, make_dev_app(settings)) as server:
        print("Dev server: patient app at http://127.0.0.1:8000/, clinician app at http://127.0.0.1:8000/clinician/, admin console at http://127.0.0.1:8000/admin/")
        server.serve_forever()
