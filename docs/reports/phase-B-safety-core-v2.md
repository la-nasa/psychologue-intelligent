# PHASE REPORT

Phase : B (V2) — Portage du cœur de sûreté
Date : 2026-08-29
Objectif : Porter la logique de sûreté indépendante du LLM de la v1 (`crisis.py`, `policy.py`, `pipeline.py`, `alerts.py`, `ai.py`, `notifications.py`, `responder.py`) dans le monolithe V2 (`server/app/`), **avec ses tests d'invariants écrits en premier**, sur PostgreSQL + tenant + RLS. Le code v1 correspondant reste en place jusqu'à la parité complète (strangler, ADR-006).

STATUS : **PASS** — invariants portés et vérifiés ; `docker compose` + `pytest` verts.

---

## 1. Ce qui est porté

| v1 | v2 | Nature |
| --- | --- | --- |
| `backend/app/policy.py` | `server/app/domain/safety/policy.py` | pur — quasi verbatim |
| `backend/app/crisis.py` | `server/app/domain/safety/crisis.py` | pur — quasi verbatim |
| `backend/app/responder.py` | `server/app/domain/safety/responder.py` | pur — invariant de routage ORANGE/RED |
| `backend/app/ai.py` (ports + `KeywordRiskModel`, `TemplatedSupportiveResponder`) | `server/app/ai/providers/{base,keyword_risk,templated}.py` | pur |
| `backend/app/pipeline.py::handle_incoming_message` | `server/app/application/safety.py::evaluate_incoming_message` | **async + SQLAlchemy + scopé tenant** |
| `backend/app/alerts.py` | `server/app/application/alerts.py` | **async + transition atomique** |
| `backend/app/notifications.py` | `server/app/application/notifications.py` | **async + backoff + lettre morte** |

Politiques cliniques : copiées dans `server/config/policies/` (copie v2 pendant la migration ; cible = table `crisis_policies`, data-model-v2 §4). Chargées **une fois au démarrage** (`app.state.safety`) — une politique invalide ou non approuvée hors `development` fait échouer le boot, jamais une requête (ADR-002/004).

## 2. Schéma (migration `0002_safety`)

5 tables, toutes avec `organization_id NOT NULL` + **RLS `FORCE`** (ADR-008) : `risk_assessments`, `crisis_events`, `alerts`, `alert_actions`, `notifications`. `downgrade` complet, réversibilité vérifiée.

## 3. Invariants portés et re-vérifiés (overview-v2 §15)

| # | Invariant | Test |
| --- | --- | --- |
| 1 | Un LLM ne décide jamais d'une crise ; ORANGE/RED n'atteignent jamais un modèle génératif | `test_safety_crisis.py::test_red_and_orange_never_reach_the_llm` (moteur espion, 0 appel), `::test_green_is_the_only_level_that_reaches_the_llm` |
| — | Le moteur de crise dégrade **conservativement** quand le modèle de risque échoue (jamais GREEN) | `test_safety_crisis.py::test_model_failure_falls_back_conservatively_never_crashes` |
| — | Un modèle sur-confiant ne peut **jamais** annuler un signal de règle haut-risque | `test_safety_crisis.py::test_rule_engine_cannot_be_overridden_by_an_overconfident_model` |
| 4 | Chaque décision référence les versions de politique, règles, modèle | `test_safety_crisis.py::test_decision_always_carries_policy_rules_and_model_versions` |
| 5 | Politiques hors code, versionnées, refusées si non approuvées hors `development` | `test_safety_policy.py` (seuils inversés, non approuvée, approuvée acceptée, fichier absent) |
| 2 | Toute alerte est persistée avant publication ; livraison idempotente | `test_safety_pipeline.py::test_red_message_opens_alert_and_records_the_full_trail`, `::test_retried_message_reference_does_not_duplicate_alert_or_notification` |
| TV-15 / SEC-001 | Transition d'alerte atomique : deux cliniciens en course ne peuvent pas se clobberer — exactement un gagnant | `test_alerts.py::test_concurrent_conflicting_transitions_have_exactly_one_winner` (asyncio.gather, 2 sessions) |
| TH-06 / TM-08 | Reprise de notification avec backoff, puis **lettre morte durable** jamais reprise | `test_notifications.py` (fenêtre de backoff respectée puis succès ; dead-letter après `MAX_TOTAL_ATTEMPTS`) |
| — | Un message GREEN n'ouvre jamais d'alerte, mais la trace de risque/crise est **toujours** écrite | `test_safety_pipeline.py::test_green_message_never_opens_an_alert` |
| — | Aucun canal → notification honnêtement `SKIPPED_NO_CHANNEL`, jamais feinte `SENT` | `test_safety_pipeline.py::test_red_message_opens_alert_and_records_the_full_trail` |

## 4. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **52 tests passent** (28 Phase 2 + 24 Phase B) |
| `coverage report` | **90 %** (seuil 85 %) |
| `ruff check .` | All checks passed |
| `mypy app` | Success (37 fichiers source) |
| `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001 + 0002) |

Fichiers sous 85 % : `auth_service.py` (54 %, dette Phase 2 connue), `rbac.py` (77 %), `redis.py` (73 %), `api/health.py` (83 %), `domain/safety/policy.py` (84 % — branches d'erreur de validation). Total : **90 %**.

## 5. Ce qui n'est PAS fait (et pourquoi)

- **Pas de retrait du code v1** : `backend/app/{crisis,policy,pipeline,alerts,ai,notifications,responder}.py` restent en place et servent toujours la démo Railway. Retrait quand le moteur de conversation V2 (Phase 4) consomme le pipeline V2 et que les 4 parcours E2E du prompt maître passent sur V2.
- **Pas d'endpoint HTTP** pour le pipeline ou les transitions d'alerte : c'est de la logique applicative, câblée par le moteur de conversation (Phase 4) et le dashboard clinicien (Phase 12). `evaluate_incoming_message` et `transition_alert` sont testés directement.
- **Modèle d'émotion** : le port accepte un tuple `emotion` optionnel (observabilité, jamais décisionnel — invariant préservé) mais aucun modèle n'est encore branché (Phase 8).
- **Outbox strictement transactionnelle + worker RabbitMQ** : le port conserve le comportement v1 (retry synchrone + `retry_pending_notifications` appelable). L'outbox stricte et le consommateur RabbitMQ arrivent en Phase 10.
- **Cycle de vie d'alerte complet** (`DETECTED→CREATED→NOTIFIED→…` du prompt §32) : le port conserve le jeu de transitions v1 (`OPEN→…`). L'enrichissement est Phase 9.
- **`compose_reply`** est porté (invariant de routage) mais le seul adaptateur `LLMProvider` est `TemplatedSupportiveResponder` ; les adaptateurs local/externe (ADR-007) arrivent en Phase 4.

## 6. Fichiers créés

`server/app/domain/{,safety/}__init__.py`, `server/app/domain/safety/{policy,crisis,responder}.py`, `server/app/ai/{,providers/}__init__.py`, `server/app/ai/providers/{base,keyword_risk,templated}.py`, `server/app/application/{alerts,notifications,safety}.py`, `server/app/alembic/versions/0002_safety.py`, `server/config/policies/*.json` (copie), `server/tests/{test_safety_policy,test_safety_crisis,test_safety_pipeline,test_notifications,test_alerts}.py`, `docs/reports/phase-B-safety-core-v2.md`.

Modifiés : `server/app/infrastructure/models.py` (+5 modèles), `server/app/core/config.py` (chemins de politiques), `server/app/main.py` (chargement au boot), `server/tests/conftest.py` (truncate des tables de sûreté).

## 7. Critères de sortie — Gate Phase B

- [x] `policy.py` porté + tests de validation/approbation.
- [x] `crisis.py` porté + tests fail-safe + non-override + versions.
- [x] `responder.py` porté + test « ORANGE/RED n'atteignent jamais le LLM » (moteur espion).
- [x] `pipeline.py` porté (async/tenant) + tests trail complet / GREEN sans alerte / idempotence.
- [x] `alerts.py` porté + **test de concurrence** (exactement un gagnant).
- [x] `notifications.py` porté + tests backoff / lettre morte.
- [x] Migration `0002_safety` avec RLS, réversible.
- [x] `ruff` + `mypy` + `bandit` + `pip-audit` propres.
- [x] Couverture ≥ 85 %.
- [x] Code v1 intact (aucune régression).

## 8. Conclusion

Le cœur de sûreté est sur la stack V2, scopé au tenant, et **chacun de ses invariants est re-testé** — c'était le but de la stratégie « cœur de sûreté d'abord » (D-1). Le moteur de crise reste structurellement indépendant du LLM, les politiques restent des données versionnées et bloquantes, les transitions d'alerte sont atomiques, et la livraison de notification dégrade honnêtement. La suite logique est la **Phase 3** (plateforme utilisateur : consentement versionné, profil, onboarding, MFA enrolment) puis la **Phase 4** (moteur de conversation), qui sera le premier consommateur HTTP réel de ce pipeline.

STATUS : **PASS**.
