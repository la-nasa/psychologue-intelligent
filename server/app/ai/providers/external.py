"""Adaptateur LLM externe (chemin DEEP, ADR-007).

Cible : un endpoint OpenAI-compatible en streaming (Anthropic via son API, ou
tout fournisseur compatible). **Inerte sans configuration** : sans
`PI_LLM_EXTERNAL_API_KEY`, `health_check()` renvoie False et `stream()` lève
`ProviderUnavailable` — le `ModelRouter` bascule alors sur le local (dégradation
assumée plutôt que transfert non consenti / non disponible).

Le contenu transmis est minimisé par le `ContextBuilder` (jamais le score PHQ-9
brut, jamais les données d'un autre patient). Aucune donnée ORANGE/RED n'atteint
jamais ce chemin (la crise est décidée avant, indépendamment).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.ai.prompt import ChatMessage
from app.ai.providers.base import ProviderUnavailable
from app.core.config import get_settings

_ENDPOINTS = {
    "openai-compatible": "/chat/completions",
    "anthropic": "/chat/completions",  # via un proxy compatible ; sinon adaptateur dédié
}


class ExternalLLMProvider:
    name = "external"

    def __init__(self) -> None:
        s = get_settings()
        self._provider = s.llm_external_provider
        self._api_key = s.llm_external_api_key
        self._model = s.llm_external_model
        self._base_url = s.llm_external_base_url
        self.version = f"external:{self._provider}:{self._model}" if self._provider else "external:unconfigured"

    @property
    def configured(self) -> bool:
        return bool(self._provider and self._api_key and self._base_url)

    async def health_check(self) -> bool:
        return self.configured

    async def stream(self, messages: list[ChatMessage], *, max_tokens: int) -> AsyncIterator[str]:
        if not self.configured:
            raise ProviderUnavailable("external LLM provider is not configured")
        async for fragment in self._stream_openai_compatible(messages, max_tokens):  # pragma: no cover
            yield fragment

    async def _stream_openai_compatible(  # pragma: no cover — nécessite une vraie clé + réseau
        self, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[str]:
        path = _ENDPOINTS.get(self._provider, "/chat/completions")
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            async with client.stream("POST", path, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    raise ProviderUnavailable(f"external LLM returned {response.status_code}")
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        return
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta
