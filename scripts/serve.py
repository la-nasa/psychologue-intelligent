#!/usr/bin/env python
"""Deployment entrypoint for a platform that terminates TLS at its edge and
forwards plain HTTP (e.g. Railway). Reuses the same WSGI app assembly as
scripts/dev_server.py (API + the three static frontends on one origin), but
binds 0.0.0.0:$PORT and uses a threading WSGI server so concurrent requests
don't serialize behind wsgiref's default one-request-at-a-time handling.

Still a minimal stdlib WSGI server: no HTTP/2, no keep-alive tuning, no
worker processes. Adequate for a small supervised pilot, not for production
traffic at scale — see docs/deployment/production-readiness.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_server import make_dev_app

from backend.app.config import Settings


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main() -> None:
    settings = Settings.from_env()
    # Binding all interfaces is required here, not a default left in by accident: a
    # container platform (Railway) routes external traffic to whatever the process
    # binds inside its network namespace, which is not reachable via 127.0.0.1.
    host = os.environ.get("HOST", "0.0.0.0")  # nosec B104
    port = int(os.environ.get("PORT", "8000"))
    app = make_dev_app(settings)
    with make_server(host, port, app, server_class=ThreadingWSGIServer) as server:
        print(f"Serving on {host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
