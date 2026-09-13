# ADR-012 — Architecture hybride LLM (note redondante et incomplète)

Date : 2026-09-13
Statut : **REDONDANT ET INCOMPLET — voir [ADR-007](ADR-007-hybrid-llm-strategy.md). Ne pas implémenter tel quel.**
Origine : audit indépendant mené sur la branche `intelligent-psychologist-bdc4b`, fusionné via PR #1. Renuméroté ADR-012 (était `docs/adr/ADR-006-to-010-stack-architecture.md` §4, portait le numéro ADR-009 dans son document d'origine).

## Note de réconciliation (2026-09-13) — IMPORTANT

Cette proposition (routeur local vLLM / cloud OpenAI-Anthropic) couvre le même sujet qu'[ADR-007](ADR-007-hybrid-llm-strategy.md) (2026-08-28, déjà accepté et implémenté : `server/app/ai/routing/model_router.py`, `dialogue_policy.py`). **Elle est plus pauvre que la décision déjà en place sur un point de sécurité central : elle ne mentionne aucun consentement `AI_EXTERNAL`** avant d'envoyer une donnée patient à un fournisseur cloud, alors qu'ADR-007 conditionne strictement le chemin DEEP (externe) à ce consentement révocable, avec repli local sans transfert en son absence. Suivre cette proposition telle quelle réintroduirait un envoi non consenti de données patient vers un tiers — **régression de sécurité, pas juste redondance**. Conservé ci-dessous pour traçabilité uniquement.

## Contenu original (inchangé)

### Contexte
Besoin de flexibilité entre performance/coût (API cloud), confidentialité/contrôle (local), résilience (fallback).

### Décision
```text
Routeur intelligent →
  ├─ Modèles locaux (vLLM) pour données sensibles
  ├─ API cloud (OpenAI/Anthropic) pour complexité
  └─ Fallback CPU pour résilience
```

### Stratégie de routage
```python
class LLMRouter:
    def select_provider(self, request):
        if request.contains_sensitive_data():
            return LOCAL_MODEL
        if request.requires_deep_reasoning():
            return CLOUD_DEEP_MODEL
        if request.is_simple():
            return FAST_MODEL
        return STANDARD_MODEL
```

### Conséquences
Positives : flexibilité maximale, confidentialité préservée, coûts optimisés, résilience améliorée.
Négatives : complexité opérationnelle, monitoring multiple, latence variable.
