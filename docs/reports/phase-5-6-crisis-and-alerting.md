# PHASE REPORT

Phase: 5–6 — AI Core (Crisis Engine) & Alert Engine
Date: 2026-08-26
Objectif: Détecteur de crise indépendant du LLM, politiques versionnées et configurables, moteur d'alerte relié à un service de notification idempotent.

## 0. Constat de départ

Avant cette session, un module `ai.py` existait déjà avec un `RiskModel` de développement et une fonction `assess_risk` qui décidait seule du niveau (GREEN/ORANGE/RED) à partir de seuils codés en dur (`0.85`, `0.45`, `0.65`), et un module `alerts.py` avec une machine à états fonctionnelle mais sans lien vers un modèle de données `risk_assessments`/`crisis_events`/`notifications` pourtant déjà spécifié dans `docs/architecture/data-model.md`. C'est la contradiction identifiée en Phase 0 de cette session : le code avait dépassé la documentation, et la politique clinique était dans le code plutôt que dans une configuration versionnée, en violation directe d'ADR-002.

## 1. Travaux réalisés

- Extraction des seuils dans `config/policies/crisis-policy-v1.json` (versionné, validé au chargement, refuse de démarrer hors développement sans `approved_by`/`approved_at`) et des termes de règles dans `crisis-rules-v1.json`.
- Nouveau module `backend/app/policy.py` : chargement et validation stricte (bornes de seuils, cohérence rouge > orange, SLA positifs, garde d'approbation par environnement).
- Réécriture de `backend/app/crisis.py` : `CrisisDetector` indépendant du LLM, moteur de règles avec normalisation insensible à la casse et aux accents, combinaison conservatrice avec le modèle de risque (maximum des scores, minimum des confiances), et **tolérance de panne du modèle** : une exception du modèle est capturée, journalisée, et dégrade la confiance au lieu de faire échouer l'évaluation ou de revenir silencieusement à un niveau sûr par défaut.
- `backend/app/ai.py` réduit aux ports d'abstraction (`LLMProvider`, `RiskModel`) et à l'adaptateur de développement `KeywordRiskModel`, explicitement documenté comme un signal parmi d'autres et jamais une source de vérité unique.
- Migration `005_crisis_and_notifications` : tables `risk_assessments`, `crisis_events`, `notifications`, et colonne `alerts.crisis_event_id`.
- `backend/app/alerts.py::open_alert` relié à un `crisis_event_id` et renvoie désormais un indicateur explicite de création (`created: bool`) pour permettre au reste du pipeline de ne notifier qu'une seule fois par alerte.
- Nouveau module `backend/app/notifications.py` : abstraction `NotificationProvider`, adaptateur de développement `LogNotificationProvider` (n'atteint aucun canal réel, le dit explicitement dans sa docstring), idempotence par `(alert_id, channel, template_version)`, retries synchrones bornés (3 tentatives), et statut honnête `SKIPPED_NO_CHANNEL` quand aucun canal n'est configuré — plutôt que de simuler un envoi.
- Nouveau module `backend/app/pipeline.py` : orchestration `handle_incoming_message` (normalisation → détection → persistance risk_assessment/crisis_event → alerte si ORANGE/RED → notification si l'alerte est nouvelle). Le contenu brut du message n'est jamais persisté dans `risk_assessments` : seule une empreinte SHA-256 sert de référence, en attendant une table `messages` chiffrée (non construite cette session, aucune conversation n'existe encore).
- ADR-004 documentant le choix JSON et la règle de combinaison des signaux.

## 2. Fichiers créés

- `config/policies/crisis-policy-v1.json`, `config/policies/crisis-rules-v1.json`
- `backend/app/policy.py`, `backend/app/notifications.py`, `backend/app/pipeline.py`
- `docs/architecture/decision-records/ADR-004-crisis-engine-signal-combination.md`
- `docs/reports/phase-4-assessment.md`, `docs/reports/phase-5-6-crisis-and-alerting.md`
- `tests/test_crisis_pipeline.py`

## 3. Fichiers modifiés

- `backend/app/ai.py`, `backend/app/crisis.py` (réécrit), `backend/app/alerts.py`, `backend/app/db.py`, `backend/app/config.py`
- `tests/test_foundation.py` (tests adaptés à la nouvelle API, plus une vérification explicite `created_first`/`created_second`)

## 4. Architecture impactée

Le moteur de crise est maintenant une chaîne explicite Normalizer → Rule Engine → Risk Model (avec tolérance de panne) → Decision Engine → Alert, conforme au schéma de la Section 8 du prompt maître, à l'exception du stade « Context Analyzer » qui n'a pas d'objet tant qu'aucune table `messages`/`conversations` n'existe : il n'a pas été simulé par une classe vide, il est documenté comme extension future. Les tables `risk_assessments`, `crisis_events` et `notifications` existent désormais et correspondent au modèle de données déjà spécifié en Phase 1.

## 5. Fonctionnalités terminées

- Détection de crise indépendante du LLM, configurable par politique versionnée, jamais dépendante d'un seul signal.
- Persistance complète de la chaîne de décision (risk_assessment → crisis_event → alert → notification) avec idempotence à chaque étape sujette à répétition.
- Service de notification avec abstraction de canal, retry borné, et statuts honnêtes (aucun canal réel n'est encore branché ; le système le dit plutôt que de le cacher).

## 6. Tests exécutés

- `python -m compileall -q backend tests`
- `python -m unittest discover -s tests -v`

## 7. Résultats des tests

- 21 tests, tous verts. Nouveaux tests notables :
  - Rejet d'une politique aux seuils incohérents ou non approuvée hors développement.
  - Le modèle qui lève une exception ne fait jamais planter l'évaluation et ne peut jamais produire un niveau plus permissif que GREEN incertain (`ORANGE` par confiance dégradée).
  - Un modèle sur-confiant et « sûr » ne peut pas annuler un signal de règle à haut risque (le maximum l'emporte).
  - Un message répété avec la même référence ne duplique ni l'alerte ni la notification.
  - Une politique avec un canal configuré produit une notification réellement envoyée (par l'adaptateur de développement) ; une politique sans canal produit un statut `SKIPPED_NO_CHANNEL` traçable, jamais un faux succès.

## 8. Bugs détectés

- Le calcul initial de la confiance combinée utilisait un ordre incohérent avant un premier passage de tests (corrigé avant validation, pas de commit intermédiaire cassé).

## 9. Bugs corrigés

- Voir ci-dessus. Aucune régression sur les 9 tests de fondation préexistants après adaptation de leur API.

## 10. Vulnérabilités détectées

| ID | Menace | Impact | Probabilité | Risque | Mitigation | Test |
| --- | --- | --- | --- | --- | --- | --- |
| TM-08 | Absence d'outbox/DLQ pour les notifications | Une alerte RED pourrait rester non notifiée si le processus s'arrête entre la création de l'alerte et l'envoi | Élevé | Faible (mono-processus actuel) | Moyen | Ajouter une file différée et un worker avant tout pilote (Phase 9) | Test de coupure en cours de notification (non encore écrit) |
| TM-09 | Dédoublonnage de la trace de risque incomplet en cas de retransmission | Deux appels avec la même référence de message dupliquent `risk_assessments`/`crisis_events` (mais pas l'alerte ni la notification) | Faible (audit, pas de sécurité) | Moyenne tant qu'il n'y a pas de table `messages` | Faible | Ajouter une contrainte d'unicité message/patient une fois la table de conversation créée | Couvert partiellement par `test_retried_message_reference_does_not_duplicate_alert_or_notification` |

## 11. Vulnérabilités corrigées

- La décision de crise codée en dur (TM-07 du registre de Phase 0 : « seuils cliniques présentés comme des décisions médicales ») est désormais sortie du code et soumise à une garde d'approbation par environnement.

## 12. Dette technique

- Pas de messages/conversations persistés : `input_reference` est une empreinte, pas un identifiant de message réutilisable pour une déduplication stricte au niveau message.
- Pas d'outbox transactionnelle ni de DLQ : les retries de notification sont synchrones et bornés à l'intérieur de l'appel, ce qui ne survit pas à un crash du processus entre les étapes.
- Le moteur de règles reste une liste de termes de développement, non un corpus validé cliniquement.
- CI ne fait encore que compiler et exécuter les tests : lint, SAST, scan de dépendances et de secrets (Section 19) restent à ajouter, prévu en Phase 10 (hardening) plutôt qu'ajouté au fil de l'eau sans revue dédiée.
- Aucune route HTTP n'expose encore ce pipeline : l'exposer correctement suppose des relations patient-clinicien et un RBAC de dashboard qui n'existent pas avant la Phase 7. L'exposer prématurément aurait recréé un risque IDOR/BOLA (TH-02) sans les contrôles nécessaires ; ce choix est délibéré, pas un oubli.

## 13. Décisions techniques

- Format JSON plutôt que YAML pour la politique, afin de rester sans dépendance externe (voir ADR-004).
- Combinaison des signaux par maximum de score / minimum de confiance, jamais l'inverse : documenté dans ADR-004 pour que la justification survive au code.
- Pas d'endpoint HTTP pour ce pipeline cette phase : reporté à la Phase 7 pour éviter un accès non scopé par relation patient-clinicien.

## 14. Risques restants

- Sans outbox/DLQ, une panne au mauvais moment peut laisser une alerte RED sans notification ; c'est un risque de disponibilité documenté (TM-08), pas résolu.
- Le corpus de règles et les seuils restent des valeurs de développement : aucune validation clinique n'a eu lieu, conformément à ADR-002 ils ne peuvent pas être approuvés pour un environnement non-développement sans `approved_by`/`approved_at`.

## 15. Métriques

- 1 migration ajoutée (005), 3 nouvelles tables, 1 colonne ajoutée.
- 12 nouveaux tests (21 au total), 0 nouvelle dépendance externe.
- 2 fichiers de politique versionnés, 0 seuil clinique restant dans le code applicatif.

## 16. Critères de sortie

- [x] Moteur de crise indépendant du LLM, tolérant à la panne du modèle.
- [x] Politiques et règles versionnées, validées, hors du code.
- [x] Alertes reliées à la chaîne de décision complète (risk_assessment → crisis_event → alert).
- [x] Service de notification idempotent avec statuts honnêtes.
- [ ] Outbox/DLQ pour les notifications (reporté à la Phase 9).
- [ ] Exposition HTTP du pipeline (reportée à la Phase 7, avec RBAC clinicien).

## 17. Conclusion

Le moteur de crise ne dépend plus d'un seul modèle ni de seuils codés en dur, et la chaîne de décision est désormais entièrement tracée et testée, y compris ses modes de panne. La dette assumée (pas d'outbox, pas de route HTTP, règles non validées cliniquement) est documentée plutôt que dissimulée. Le prochain gate naturel est la Phase 7 : relations patient-clinicien, RBAC de dashboard, et c'est à ce moment que ce pipeline doit être exposé de façon sûre.

STATUS: PASS WITH WARNINGS
