"""Modèle de risque lexical — Phase 9.

Toujours **un signal parmi d'autres** pour le moteur de crise, jamais
décisionnaire seul (ADR-004). Plus large que `KeywordRiskModel` : entrée
normalisée durcie, catégories pondérées, lexique robuste à quelques variantes
phonétiques, prise en compte de rares tournures de réassurance explicites.

Ce n'est pas un modèle neuronal (pas d'infra PyTorch/entraînement ici). C'est
une amélioration honnête de la robustesse, mesurée par `tests/eval/`.
"""
from __future__ import annotations

from app.domain.safety.normalize import harden

# Formes déjà normalisées (minuscules, sans accents). Le durcissement gère
# leetspeak / espacement / allongement en amont.
_HIGH = (
    "plan suicidaire", "planifier mon suicide", "me suicider", "me tuer", "me tue",
    "je vais me tuer", "en finir", "mettre fin a mes jours", "mettre fin a ma vie",
    "veux mourir", "envie de me faire du mal", "me faire du mal ce soir",
    "acheter des medicaments pour", "prendre toutes les pilules", "prendre tous les cachets",
    "je ne veux plus me reveiller",
)
_CONCERN = (
    "envie de mourir", "plus envie de vivre", "desespere", "je n'en peux plus",
    "a quoi bon", "tout le monde serait mieux sans moi", "je suis un fardeau",
    "je me sens vide", "sans issue", "je n'ai plus d'espoir", "je suis au bout",
)
# Tournures de réassurance explicites — rares, formulées prudemment.
_REASSURANCE = (
    "je ne veux pas mourir", "je n'ai pas de pensees suicidaires", "aucune envie de me faire du mal",
    "je ne pense pas au suicide", "je ne ferais jamais ca",
)


class LexiconRiskModel:
    version = "lexicon-risk-1"

    def predict(self, text: str) -> tuple[float, float]:
        h = harden(text)
        despaced = h.replace(" ", "")

        def present(terms: tuple[str, ...]) -> bool:
            return any(t in h or t.replace(" ", "") in despaced for t in terms)

        if present(_REASSURANCE) and not present(_HIGH):
            return 0.05, 0.75

        if present(_HIGH):
            return 0.95, 0.85
        if present(_CONCERN):
            return 0.6, 0.7
        # Absence de terme : lecture assez confiante pour un lexique (rien d'ambigu).
        return 0.05, 0.85
