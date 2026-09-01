"""Ports modèles — porté/étendu de v1 `backend/app/ai.py` (overview-v2 §8, ADR-007).

Le système n'est jamais couplé à un fournisseur. `LLMProvider` (sync) est
conservé pour le pipeline de sûreté / `compose_reply`. `StreamingLLMProvider`
(async) est utilisé par le moteur de conversation : plusieurs adaptateurs
(`local`, `external`), choisis par le `ModelRouter`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.ai.prompt import ChatMessage


class LLMProvider(Protocol):
    version: str

    def generate(self, text: str, context: dict | None = None) -> str: ...


class RiskModel(Protocol):
    version: str

    def predict(self, text: str) -> tuple[float, float]: ...


class ProviderUnavailable(RuntimeError):
    """Un fournisseur non configuré ou injoignable. Le routeur bascule en repli."""


class StreamingLLMProvider(Protocol):
    name: str          # "local" | "external" — tracé sur chaque message (messages.llm_provider)
    version: str

    async def health_check(self) -> bool: ...

    def stream(self, messages: list[ChatMessage], *, max_tokens: int) -> AsyncIterator[str]:
        """Émet des fragments de texte. Peut lever ``ProviderUnavailable``."""
        ...
