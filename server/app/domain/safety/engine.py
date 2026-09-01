"""SafetyEngine — vue d'ensemble des composants (master prompt §28, overview-v2 §7).

Le moteur de sûreté n'est **pas** un objet monolithique : c'est la composition
de plusieurs unités, chacune indépendante du LLM et testée séparément.

    RuleEngine        -> domain/safety/crisis._rule_signal  (termes versionnés)
    RiskClassifier    -> ai/providers/base.RiskModel        (port ; KeywordRiskModel, modèle entraîné futur)
    CrisisDetector    -> domain/safety/crisis.CrisisDetector (combine max score / min confiance ; UNKNOWN -> ORANGE)
    PolicyEngine      -> domain/safety/policy.load_crisis_*  (seuils/SLA versionnés, bloqués si non approuvés)
    EscalationEngine  -> application/escalation.escalate     (décision -> alerte idempotente + SLA + notification)
    OutputSafety      -> application/output_safety.check     (PII / clinique / auto-agression / cohérence / fuite -> SAFE_FALLBACK)

Invariants (re-testés à chaque phase) :
1. La classification de crise a lieu AVANT toute génération et n'utilise jamais un LLM.
2. ORANGE/RED -> gabarit fixe versionné ; aucun fournisseur LLM n'est appelé.
3. Une défaillance du modèle de risque n'abaisse jamais la prudence.
4. Toute décision référence les versions de politique, règles et modèle.
5. `OutputSafety` s'applique à toute réponse générée ; son échec -> SAFE_FALLBACK, jamais la sortie brute.
"""
from __future__ import annotations

COMPONENTS = (
    "RuleEngine",
    "RiskClassifier",
    "CrisisDetector",
    "PolicyEngine",
    "EscalationEngine",
    "OutputSafety",
)
