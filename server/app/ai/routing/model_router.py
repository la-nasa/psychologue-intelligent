"""Model Router (master prompt §106, ADR-007).

Choisit le fournisseur pour un message GREEN :
- FAST                    -> local
- DEEP + consentement AI_EXTERNAL actif + fournisseur externe disponible -> external
- DEEP sinon              -> local (dégradation assumée, jamais de transfert non consenti)

INVARIANT (overview-v2 §15 invariants 7 & 8) : ce routeur n'est jamais atteint
pour un message ORANGE/RED, et le chemin externe exige toujours le consentement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.providers.base import StreamingLLMProvider

LOGGER = logging.getLogger("pi.ai.router")


@dataclass(frozen=True)
class Providers:
    local: StreamingLLMProvider
    external: StreamingLLMProvider


@dataclass(frozen=True)
class Route:
    provider: StreamingLLMProvider
    effective_path: str   # "FAST" | "DEEP" — ce qui a réellement été utilisé
    reason: str


async def route(
    *,
    requested_path: str,
    has_ai_external_consent: bool,
    providers: Providers,
) -> Route:
    if requested_path == "DEEP" and has_ai_external_consent and await providers.external.health_check():
        return Route(provider=providers.external, effective_path="DEEP", reason="deep_external")

    if requested_path == "DEEP":
        if not has_ai_external_consent:
            reason = "deep_downgraded_no_consent"
        else:
            reason = "deep_downgraded_external_unavailable"
        LOGGER.info("DEEP request served locally: %s", reason)
        return Route(provider=providers.local, effective_path="FAST", reason=reason)

    return Route(provider=providers.local, effective_path="FAST", reason="fast_local")
