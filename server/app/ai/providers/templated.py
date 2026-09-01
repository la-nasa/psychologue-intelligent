"""Répondeur non génératif de développement — porté de v1 `backend/app/ai.py`.

Substitut derrière le port `LLMProvider`. Ne lit ni ne raisonne sur le message
au-delà du choix d'un index de rotation : ce n'est pas une IA conversationnelle
et ne doit jamais être présenté comme telle. Ne s'exécute que pour les messages
GREEN (les réponses de crise viennent de gabarits fixes — voir
`domain/safety/responder.py`). Le répondeur génératif auto-hébergé (ADR-005/007)
sera un autre adaptateur `LLMProvider`, ajouté en Phase 4.
"""
from __future__ import annotations


class TemplatedSupportiveResponder:
    version = "templated-responder-dev-1"

    def __init__(self, acknowledgments: tuple[str, ...]) -> None:
        if not acknowledgments:
            raise ValueError("at least one acknowledgment template is required")
        self.acknowledgments = acknowledgments

    def generate(self, text: str, context: dict | None = None) -> str:
        # `context` est délibérément ignoré : le contrat de cette classe est une
        # rotation fixe, jamais du texte personnalisé.
        index = sum(text.encode("utf-8")) % len(self.acknowledgments)
        return self.acknowledgments[index]
