"""FAST path local hybride (ADR-015).

Ordre : serveur OpenAI-compatible (vLLM / llama.cpp server) → GGUF
in-process → gabarits ``LocalSupportiveResponder``. ``llama_cpp`` n'est
importé qu'à l'ouverture d'un fichier GGUF, jamais au chargement du module.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.ai.prompt import ChatMessage
from app.ai.providers.base import ProviderUnavailable
from app.ai.providers.local import LocalSupportiveResponder
from app.core.config import Settings, get_settings

LOGGER = logging.getLogger("pi.ai.local")


class ChatEngine(Protocol):
    """Surface minimale de llama.cpp, injectable en tests."""

    def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        stream: bool = False,
    ) -> Any: ...


def _default_engine_factory(
    model_path: Path, context_tokens: int, n_gpu_layers: int, n_threads: int | None
) -> ChatEngine:
    from llama_cpp import Llama  # type: ignore[import-not-found]

    kwargs: dict[str, Any] = {
        "model_path": str(model_path),
        "n_ctx": context_tokens,
        "n_gpu_layers": n_gpu_layers,
        "verbose": False,
    }
    if n_threads is not None:
        kwargs["n_threads"] = n_threads
    return Llama(**kwargs)


class HybridLocalProvider:
    """``StreamingLLMProvider`` local : HTTP, puis GGUF, puis gabarits."""

    name = "local"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        fallback: LocalSupportiveResponder | None = None,
        engine_factory: Callable[[Path, int, int, int | None], ChatEngine] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._fallback = fallback or LocalSupportiveResponder()
        self._engine_factory = engine_factory or _default_engine_factory
        self._http = http_client
        self._engine: ChatEngine | None = None
        self._lock = threading.RLock()
        self.version = self._initial_version()

    def _initial_version(self) -> str:
        if self._settings.llm_base_url:
            return f"local:openai-compat:{self._settings.fast_model}"
        if self._gguf_usable():
            return f"local-gguf:{self._settings.llm_model_path.stem}"
        return self._fallback.version

    def _gguf_usable(self) -> bool:
        if self._settings.env == "testing" and not self._settings.llm_enable_in_tests:
            return False
        path = self._settings.llm_model_path
        return path.is_file() and path.stat().st_size > 0

    def _threads(self) -> int | None:
        threads = self._settings.llm_threads
        if threads is None:
            override = os.environ.get("PI_LLM_THREADS")
            threads = int(override) if override else None
        return threads

    def _ensure_engine(self) -> ChatEngine:
        with self._lock:
            if self._engine is None:
                self._engine = self._engine_factory(
                    self._settings.llm_model_path,
                    self._settings.llm_context_tokens,
                    self._settings.llm_n_gpu_layers,
                    self._threads(),
                )
            return self._engine

    async def warmup(self) -> None:
        """Charge le GGUF hors requête utilisateur (TTFT du premier tour)."""
        if not self._gguf_usable():
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_engine)
        LOGGER.info("GGUF engine warmed", extra={"version": self.version})

    async def health_check(self) -> bool:
        if await self._remote_healthy():
            return True
        return self._gguf_usable()

    async def _remote_healthy(self) -> bool:
        base = self._settings.llm_base_url.rstrip("/")
        if not base:
            return False
        headers = {"Authorization": f"Bearer {self._settings.llm_api_key}"}
        client = self._http
        try:
            if client is None:
                async with httpx.AsyncClient(base_url=base, timeout=2.0) as owned:
                    response = await owned.get("/models", headers=headers)
            else:
                response = await client.get("/models", headers=headers)
            return response.status_code < 400
        except Exception:
            LOGGER.info("local OpenAI-compat health_check failed", exc_info=True)
            return False

    async def stream(self, messages: list[ChatMessage], *, max_tokens: int) -> AsyncIterator[str]:
        if await self._remote_healthy():
            try:
                self.version = f"local:openai-compat:{self._settings.fast_model}"
                async for fragment in self._stream_remote(messages, max_tokens):
                    yield fragment
                return
            except Exception:
                LOGGER.exception("local OpenAI-compat stream failed; trying GGUF / templates")

        if self._gguf_usable():
            try:
                self.version = f"local-gguf:{self._settings.llm_model_path.stem}"
                async for fragment in self._stream_gguf(messages, max_tokens):
                    yield fragment
                return
            except Exception:
                LOGGER.exception("GGUF stream failed; falling back to templates")

        self.version = self._fallback.version
        LOGGER.info("local generative backends unavailable; using supportive templates")
        async for fragment in self._fallback.stream(messages, max_tokens=max_tokens):
            yield fragment

    async def _stream_remote(self, messages: list[ChatMessage], max_tokens: int) -> AsyncIterator[str]:
        base = self._settings.llm_base_url.rstrip("/")
        payload = {
            "model": self._settings.fast_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        client = self._http
        emitted = False
        if client is None:
            async with httpx.AsyncClient(base_url=base, timeout=60.0) as owned:
                async for fragment in self._iter_sse(owned, payload, headers):
                    emitted = True
                    yield fragment
        else:
            async for fragment in self._iter_sse(client, payload, headers):
                emitted = True
                yield fragment
        if not emitted:
            raise ProviderUnavailable("local OpenAI-compat returned no tokens")

    async def _iter_sse(
        self, client: httpx.AsyncClient, payload: dict, headers: dict
    ) -> AsyncIterator[str]:
        async with client.stream("POST", "/chat/completions", json=payload, headers=headers) as response:
            if response.status_code >= 400:
                raise ProviderUnavailable(f"local OpenAI-compat returned {response.status_code}")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ").strip()
                if data == "[DONE]":
                    return
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if delta:
                    yield delta

    async def _stream_gguf(self, messages: list[ChatMessage], max_tokens: int) -> AsyncIterator[str]:
        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()
        payload = [dict(m) for m in messages]

        def _run() -> None:
            try:
                engine = self._ensure_engine()
                with self._lock:
                    chunks: Iterator[Any] = engine.create_chat_completion(
                        messages=payload,
                        max_tokens=max_tokens,
                        temperature=0.65,
                        stream=True,
                    )
                    for chunk in chunks:
                        try:
                            delta = chunk["choices"][0]["delta"].get("content")
                        except (KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            queue.put_nowait(delta)
                queue.put_nowait(None)
            except Exception as exc:
                queue.put_nowait(exc)

        loop = asyncio.get_running_loop()
        worker = loop.run_in_executor(None, _run)
        emitted = False
        try:
            while True:
                item = await queue.get()
                if isinstance(item, BaseException):
                    raise item
                if item is None:
                    break
                emitted = True
                yield item
        finally:
            await worker
        if not emitted:
            raise ProviderUnavailable("GGUF engine returned no tokens")
