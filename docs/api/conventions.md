# Contrats et conventions API

La spécification exécutable est [`openapi.yaml`](openapi.yaml) (34 opérations, validée par `scripts/validate_openapi.py` en CI). Ce document-ci donne les principes transverses ; en cas de divergence, `openapi.yaml` prévaut puisqu'il est écrit directement à partir des routes de `backend/app/http.py`, ligne par ligne.

## Principes

- REST JSON sous `/api/v1`, TLS obligatoire ; OpenAPI est la source de vérité des contrats d’interface.
- Erreurs RFC 9457 (`application/problem+json`) avec `trace_id`, jamais de données sensibles.
- UUID en chaîne, dates ISO 8601 UTC, pagination curseur ; limites explicites de taille et de débit.
- Authentification et autorisation serveur avant toute lecture/écriture ; aucune permission implicite par l’interface.
- Commandes à effet externe avec `Idempotency-Key`; événements publiés via outbox après transaction.

## Frontières de commandes

| Commande | Préconditions clés | Effets audités |
| --- | --- | --- |
| `POST /auth/sessions` | rate limit, mot de passe/mfa valides | session rotation/revocation |
| `POST /consents` | patient authentifié, version présentée | preuve de consentement |
| `POST /conversations/{id}/messages` | participant, consentement conversationnel | message, évaluation risque, alerte éventuelle |
| `POST /assessments/phq9` | patient autorisé, instrument publié | score calculé côté serveur |
| `POST /alerts/{id}/actions` | clinicien lié, transition autorisée | action, justification, audit |
| `POST /admin/policies` | MFA renforcé, permission dédiée | version de politique en brouillon |

## Événements de domaine

`message.received`, `risk.assessed`, `crisis.detected`, `alert.opened`, `alert.acknowledged`, `notification.requested`, `consent.revoked`, `model.approval.requested`, `model.deployment.rolled_back`.

Chaque événement contient `event_id`, `occurred_at`, `correlation_id`, `schema_version`, `actor_ref`, `resource_ref` et une charge minimisée. Le contenu clinique est référencé par un identifiant d’accès contrôlé, non recopié dans la queue.

