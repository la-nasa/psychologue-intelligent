"""Tests du FAST path local hybride (ADR-015) — fakes HTTP et llama.cpp."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.ai.prompt import ChatMessage
from app.ai.providers.generative_local import HybridLocalProvider
from app.ai.providers.local import LocalSupportiveResponder
from app.core.config import Settings

_MESSAGES: list[ChatMessage] = [
    {"role": "system", "content": "tu es un accompagnant"},
    {"role": "user", "content": "bonjour"},
]


def _settings(**overrides: object) -> Settings:
    base = {
        "env": "testing",
        "llm_enable_in_tests": False,
        "llm_base_url": "",
        "llm_model_path": Path("work/models/missing.gguf"),
        "otel_enabled": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


async def test_health_check_false_without_backend() -> None:
    provider = HybridLocalProvider(settings=_settings())
    assert await provider.health_check() is False


async def test_stream_falls_back_to_templates_when_unhealthy() -> None:
    provider = HybridLocalProvider(settings=_settings())
    assert await provider.health_check() is False
    chunks = [part async for part in provider.stream(_MESSAGES, max_tokens=40)]
    text = "".join(chunks)
    assert "Merci" in text or "entends" in text
    assert provider.version == LocalSupportiveResponder.version


async def test_remote_stream_when_openai_compat_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "Qwen/Qwen2.5-3B-Instruct"}]})
        body = 'data: {"choices":[{"delta":{"content":"Bonjour"}}]}\n\ndata: {"choices":[{"delta":{"content":" là"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    settings = _settings(llm_base_url="http://llm.test/v1", fast_model="Qwen/Qwen2.5-3B-Instruct")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://llm.test/v1") as client:
        provider = HybridLocalProvider(settings=settings, http_client=client)
        assert await provider.health_check() is True
        text = "".join([part async for part in provider.stream(_MESSAGES, max_tokens=40)])
    assert text == "Bonjour là"
    assert provider.version.startswith("local:openai-compat:")


async def test_remote_unhealthy_falls_through_to_templates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    settings = _settings(llm_base_url="http://llm.test/v1")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://llm.test/v1") as client:
        provider = HybridLocalProvider(settings=settings, http_client=client)
        assert await provider.health_check() is False
        text = "".join([part async for part in provider.stream(_MESSAGES, max_tokens=40)])
    assert text
    assert provider.version == LocalSupportiveResponder.version


class _FakeLlama:
    def create_chat_completion(self, messages, max_tokens, temperature, stream=False):  # noqa: ANN001
        assert stream is True
        assert messages[-1]["content"] == "bonjour"

        def chunks() -> Iterator[dict]:
            yield {"choices": [{"delta": {"content": "Salut"}}]}
            yield {"choices": [{"delta": {"content": " !"}}]}

        return chunks()


async def test_gguf_stream_uses_injected_engine(tmp_path: Path) -> None:
    weights = tmp_path / "toy.gguf"
    weights.write_bytes(b"not-a-real-model")
    settings = _settings(llm_enable_in_tests=True, llm_model_path=weights)

    def factory(path: Path, ctx: int, layers: int, threads: int | None) -> _FakeLlama:
        assert path == weights
        return _FakeLlama()

    provider = HybridLocalProvider(settings=settings, engine_factory=factory)
    assert await provider.health_check() is True
    text = "".join([part async for part in provider.stream(_MESSAGES, max_tokens=20)])
    assert text == "Salut !"
    assert provider.version == "local-gguf:toy"


@pytest.mark.llm
async def test_real_gguf_optional_smoke() -> None:
    """Hors CI : un GGUF réel sur PI_LLM_MODEL_PATH + extra ``llm``."""
    import os

    path = Path(os.environ.get("PI_LLM_MODEL_PATH", "work/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"))
    if not path.is_file():
        pytest.skip("no GGUF at PI_LLM_MODEL_PATH")
    pytest.skip("opt-in measurement only — use scripts/benchmark_llm_ttft.py")
