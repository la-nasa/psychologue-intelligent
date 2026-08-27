#!/usr/bin/env python
"""Sequential latency baseline for key operations, on this machine, against the
SQLite dev backend. This is not a load test and not a CI gate: single-process
timings on a shared dev machine are too noisy to assert thresholds on, and
wsgiref's single-threaded server means it says nothing about real concurrent
throughput. It exists to catch an obvious regression (e.g. an accidental N+1
query) by eyeballing the numbers, and to give an honest, dated snapshot in the
phase report rather than an unmeasured claim.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.http import application

N = 200


def invoke(app, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1"):
    result = {}
    headers = headers or {}
    environ = {
        "REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": BytesIO(body),
        "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": headers.get("Content-Type", ""),
        "REMOTE_ADDR": remote_addr,
    }
    if "Authorization" in headers:
        environ["HTTP_AUTHORIZATION"] = headers["Authorization"]

    def start_response(status, response_headers):
        result["status"] = status

    payload = b"".join(app(environ, start_response))
    return result["status"], payload


def _expect_created(status: str) -> None:
    # Not `assert`: this script can be run under `python -O`, which strips
    # asserts entirely, silently turning a failed call into a missing sample
    # instead of a loud failure.
    if status != "201 Created":
        raise RuntimeError(f"expected 201 Created, got {status}")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = min(int(len(ordered) * p), len(ordered) - 1)
    return ordered[index]


def report(name: str, durations_ms: list[float]) -> None:
    print(f"{name:<32} n={len(durations_ms):<5} mean={statistics.mean(durations_ms):6.2f}ms "
          f"p50={percentile(durations_ms, 0.50):6.2f}ms p95={percentile(durations_ms, 0.95):6.2f}ms "
          f"max={max(durations_ms):6.2f}ms")


def main() -> None:
    temp = TemporaryDirectory()
    settings = Settings(database_path=Path(temp.name) / "bench.db", password_iterations=1_000)
    app = application(settings)

    durations = []
    for i in range(N):
        body = json.dumps({"email": f"bench{i}@example.test", "password": "correct horse battery"}).encode()  # nosec B105 -- test fixture password, not a real credential
        # distinct fake source per call: the registration rate limiter (10/hour
        # per IP, see http.py) would otherwise dominate this benchmark's numbers
        start = time.perf_counter()
        status, _ = invoke(app, "POST", "/api/v1/auth/register", body, {"Content-Type": "application/json"}, remote_addr=f"10.0.{i // 256}.{i % 256}")
        durations.append((time.perf_counter() - start) * 1000)
        _expect_created(status)
    report("register", durations)

    tokens = []
    durations = []
    for i in range(N):
        body = json.dumps({"email": f"bench{i}@example.test", "password": "correct horse battery"}).encode()  # nosec B105 -- test fixture password, not a real credential
        start = time.perf_counter()
        status, payload = invoke(app, "POST", "/api/v1/auth/sessions", body, {"Content-Type": "application/json"})
        durations.append((time.perf_counter() - start) * 1000)
        _expect_created(status)
        tokens.append(json.loads(payload)["access_token"])
    report("login", durations)

    durations = []
    for token in tokens:
        auth = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        start = time.perf_counter()
        status, _ = invoke(app, "POST", "/api/v1/assessments/phq9", json.dumps({"answers": [1] * 9}).encode(), auth)
        durations.append((time.perf_counter() - start) * 1000)
        _expect_created(status)
    report("phq9 submit", durations)

    conversation_ids = []
    durations = []
    for token in tokens:
        auth = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        invoke(app, "POST", "/api/v1/consents", b'{"purpose":"CARE","version":"1"}', auth)
        start = time.perf_counter()
        status, payload = invoke(app, "POST", "/api/v1/conversations", b"{}", auth)
        durations.append((time.perf_counter() - start) * 1000)
        _expect_created(status)
        conversation_ids.append(json.loads(payload)["id"])
    report("start conversation", durations)

    durations = []
    for token, conversation_id in zip(tokens, conversation_ids, strict=True):
        auth = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        start = time.perf_counter()
        status, _ = invoke(app, "POST", f"/api/v1/conversations/{conversation_id}/messages", json.dumps({"text": "Ma journee etait plutot calme aujourd'hui"}).encode(), auth)
        durations.append((time.perf_counter() - start) * 1000)
        _expect_created(status)
    report("send message (full crisis+emotion pipeline)", durations)

    app.close()
    temp.cleanup()


if __name__ == "__main__":
    main()
