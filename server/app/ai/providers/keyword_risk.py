"""Modèle de risque déterministe de développement — porté de v1 `backend/app/ai.py`.

Jamais un modèle clinique. Une implémentation interchangeable derrière le port
`RiskModel`. Le moteur de crise traite sa sortie comme un signal parmi d'autres.
"""
from __future__ import annotations


class KeywordRiskModel:
    version = "keyword-risk-dev-1"
    high_risk_terms = ("plan suicidaire", "me tuer", "suicide", "acheter des medicaments")
    concern_terms = ("envie de mourir", "plus envie de vivre", "desespere")

    def predict(self, text: str) -> tuple[float, float]:
        normalized = text.casefold()
        if any(term in normalized for term in self.high_risk_terms):
            return 0.95, 0.70
        if any(term in normalized for term in self.concern_terms):
            return 0.60, 0.60
        # L'absence de terme est une lecture assez confiante pour un matcher de
        # mots-clés (rien d'ambigu), pas une supposition peu sûre : 0.85, au-dessus
        # du plancher de confiance ORANGE par défaut (0.65).
        return 0.05, 0.85
