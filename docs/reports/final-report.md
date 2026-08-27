# RAPPORT FINAL DE PROJET — Psychologue Intelligent

Date : 2026-08-27
Version : 0.1.0-dev (pré-pilote, non déployée)
Statut : voir Section 26

Ce rapport synthétise 16 rapports de phase (`docs/reports/phase-0-*` à `phase-13-*`), le rapport de mission d'audit de sécurité (`docs/reports/phase-14-security-audit-mission.md`), plus ce rapport. Il ne répète pas leur contenu en détail : il pointe vers eux et tire les conclusions transverses. En cas de divergence entre ce rapport et un rapport de phase ou le code, **le code et ses tests font foi**, pas ce document.

**Addendum post-Phase 14 (2026-08-27)** : un audit de sécurité méthodique (OWASP/CWE/STRIDE) a depuis trouvé et corrigé 3 vulnérabilités réelles (SEC-001 à SEC-003, la plus sérieuse une race condition contournant l'invariant « un rejet clinique bloque définitivement un modèle » — voir `docs/security/security-assessment-report.md`), et un worker de reprise de notifications avec backoff exponentiel et lettre morte explicite (`scripts/retry_notifications.py`) a réduit sans totalement fermer TM-08. Les chiffres ci-dessous (Sections 11–12) ont été mis à jour en conséquence ; le reste du corps du rapport date d'avant cet audit et n'a pas été réécrit dans son intégralité.

## 1. Résumé exécutif

Une fondation logicielle complète et testée existe pour un pilote « Psychologue Intelligent » supervisé : authentification à double facteur, moteur de détection de crise indépendant du LLM, tableau de bord clinicien, console d'administration, cœur conversationnel non génératif, un modèle d'émotion réellement entraîné (observabilité uniquement), et un pipeline d'apprentissage continu complet avec consentement révocable et double approbation clinique. 95 tests automatisés couvrent 93 % du code applicatif, incluant une suite adversariale de sécurité et 4 parcours de bout en bout automatisés. Un bug de concurrence critique a été trouvé et corrigé avant qu'il n'affecte un déploiement réel, puis un audit de sécurité dédié en a trouvé et corrigé trois autres (SEC-001 à SEC-003). **Rien de tout cela ne constitue une validation clinique** : aucun psychologue, psychiatre ou comité d'éthique n'a examiné le système, et aucune donnée patient réelle n'a jamais transité par ce projet.

## 2. Architecture

Monolithe modulaire API-first (ADR-001), frontières de domaine imposées dans le code plutôt que par des services séparés, choisi pour réduire la surface d'attaque et la complexité opérationnelle d'un pilote (voir `docs/reports/phase-0-audit.md`). Diagramme logique et flux critiques : `docs/architecture/overview.md`. Modèle de données : `docs/architecture/data-model.md`. Décisions d'architecture actées : `docs/architecture/decision-records/ADR-001` à `ADR-004`.

## 3. Modules livrés

| Domaine | Module(s) | Phase |
| --- | --- | --- |
| Identité, authentification, autorisation, audit | `auth.py`, `security.py`, `http.py` | 2 |
| Patients, consentement, confidentialité | `auth.py` (profils/consentements), migrations 002 | 3 |
| Évaluation PHQ-9 | `phq9.py` | 4 |
| Moteur de risque et de crise | `crisis.py`, `ai.py`, `policy.py`, `pipeline.py`, `alerts.py`, `notifications.py` | 5–6 |
| Tableau de bord clinicien, relations patient-clinicien | `clinician.py` | 7 |
| Cœur conversationnel | `conversation.py`, `responder.py` | 8a |
| Modèle d'émotion (observabilité) | `emotion.py`, `ml/train_emotion_classifier.py` | 8 |
| Apprentissage continu, registre de modèles | `learning.py` | 8b |
| Console d'administration | `admin.py` | 23 |
| Durcissement, résilience, E2E | tests transverses, pas de nouveau module métier | 10–13 |

## 4. Pile technique

Backend : Python 3.12+, bibliothèque standard uniquement en exécution (aucune dépendance runtime — ADR-003). Base de données : SQLite (développement), PostgreSQL requis avant pilote (`production-readiness.md`). Frontend : HTML/CSS/JS vanilla, trois applications statiques (patient, clinicien, admin) servies sur une origine commune en développement (`scripts/dev_server.py`). Outillage de développement séparé du runtime : `ruff`, `mypy`, `bandit`, `pip-audit`, `coverage`, `PyYAML` (extra `dev`), `scikit-learn` (extra `ml`, entraînement uniquement).

## 5. Base de données

10 migrations (`backend/app/db.py::MIGRATIONS`), additives uniquement, jamais réécrites après application (garanti par `schema_migrations` + `test_migration_is_idempotent`). Schéma complet documenté dans `docs/architecture/data-model.md`. Rollback de schéma : manuel, voir `docs/deployment/rollback.md` Section 2 — limite assumée, pas cachée.

## 6. API

Spécification exécutable complète : [`docs/api/openapi.yaml`](../api/openapi.yaml), 34 opérations, validée par `scripts/validate_openapi.py` (CI). Conventions transverses : `docs/api/conventions.md`. Toutes les erreurs suivent RFC 9457 ; aucune route n'expose de trace de pile (`test_security.py::PayloadAndContentTypeAbuseTests`).

## 7. Architecture IA

Abstraction `ModelProvider` respectée : `LLMProvider`, `RiskModel`, `EmotionModel` sont des ports interchangeables (`ai.py`, `crisis.py`, `emotion.py`), jamais couplés en dur. Le LLM (actuellement un répondeur non génératif, décision explicite de l'utilisateur en Phase 8a) ne décide jamais d'une situation de crise : `responder.py::compose_reply` route les niveaux ORANGE/RED vers des gabarits fixes versionnés, jamais vers le répondeur. Le modèle d'émotion (Phase 8, GoEmotions/Apache-2.0, 69 % d'exactitude test réelle) est strictement observabilité — `crisis.CrisisDetector` ne le référence jamais. Détail complet : `docs/reports/phase-8-emotion-classifier.md`, `ml/MODEL_CARD.md`.

## 8. Architecture de sécurité

PBKDF2-HMAC-SHA256 (600 000 itérations) pour les mots de passe — pas Argon2id, écart assumé depuis l'ADR-003 (dépendance non ajoutée sans justification suffisante), documenté dans le threat model. MFA obligatoire pour CLINICIAN et ADMIN. RBAC vérifié côté serveur à chaque appel, jamais déduit du client. Rate limiting sur le login, l'inscription et l'envoi de message (Phase 10). Aucune donnée sensible en cookie (architecture par jeton `Bearer`, CSRF classique sans objet par construction).

## 9. Threat model

`docs/security/threat-model.md` — 13 menaces STRIDE/OWASP, chacune avec un statut de vérification tracé vers un test réel (pas une déclaration d'intention). Un bug de disponibilité critique (TH-13, connexion SQLite partagée entre threads) a été trouvé et corrigé en Phase 11–12.

## 10. Confidentialité

Consentement CARE/LEARNING séparé et **révocable** (la révocation a été ajoutée en Phase 8b après avoir constaté qu'elle manquait). Échantillonnage d'apprentissage strictement limité aux patients consentants au moment de l'échantillonnage. Anonymisation par motifs (e-mail, téléphone) en premier filtre, revue humaine obligatoire ensuite — jamais l'inverse. Limite assumée : pas de détection de PII non structurée (noms propres, adresses) ; pas de retrait rétroactif d'un dataset déjà finalisé (immutabilité délibérée pour la traçabilité, en tension documentée avec un droit de retrait total).

## 11. Tests

95 tests automatisés répartis sur 10 fichiers (`tests/`) : fondation, PHQ-9, moteur de crise (incluant la reprise de notifications en échec), tableau de bord clinicien, console d'administration, conversation, modèle d'émotion, pipeline d'apprentissage, sécurité adversariale (incluant 3 races conditions reproduites puis corrigées), résilience/concurrence, parcours E2E. Chaque fichier correspond à un domaine ou à une classe de vérification transverse, jamais à une phase de développement (les tests survivent aux phases qui les ont écrits).

## 12. Couverture de tests

93 % sur `backend/app` (seuil CI : 85 %, réel : 93 %). Fichiers sous 90 % : `config.py` (70 %, code de câblage d'environnement peu risqué), `policy.py` (84 %, branches de validation d'erreur), `learning.py` (87 %), `clinician.py`/`auth.py`/`security.py` (89–90 %). `notifications.py` (retry inclus) : 97 %.

## 13. Résultats des tests de sécurité

`tests/test_security.py` (29 tests) : injection SQL contre le login (échoue, comme attendu), payload `<script>` stocké tel quel jamais interprété, contournement d'authentification (jeton manquant/malformé/trafiqué/révoqué), traversée de chemin contre le serveur de développement, élévation de privilèges (champ `role` injecté ignoré), rate limiting (login/inscription/message/PHQ-9), non-fuite de secret (`password_hash`/`mfa_secret` jamais renvoyés, pas d'énumération de compte), en-têtes de sécurité complets sur toutes les réponses, et 3 races conditions métier reproduites de façon déterministe puis corrigées (verrouillage optimiste). Audit XSS manuel des trois frontends : 0 faille trouvée. Détail : `docs/reports/phase-10-security-hardening.md` et `docs/security/security-assessment-report.md` (audit complet post-Phase 14).

## 14. Résultats des tests de sécurité IA

Sans objet au sens classique (jailbreak/prompt injection) tant qu'aucun LLM génératif n'est intégré — voir threat model TH-04. Ce qui a été vérifié à la place : le modèle d'émotion ne peut structurellement pas influencer une décision de crise (`test_emotion_model.py::EmotionObservabilityIsNeverDecisiveTests`), et un modèle de risque défaillant dégrade la confiance sans jamais faire planter le pipeline (`test_crisis_pipeline.py::CrisisDetectorFailSafeTests`).

## 15. Résultats de performance

Mesure séquentielle ponctuelle sur une machine de développement partagée (`scripts/benchmark.py`, non utilisée comme porte de CI) : 13–25 ms en moyenne selon l'opération, dont l'essentiel est le hachage PBKDF2 volontairement coûteux, pas la base de données. Coût de la connexion SQLite par requête isolé à ~3 ms. **Aucun test de charge réel** (montée en charge, pic, endurance) n'a été effectué — hors de portée sans infrastructure dédiée. Détail : `docs/reports/phase-11-12-performance-resilience.md`.

## 16. Résultats de résilience

Bug de concurrence critique trouvé et corrigé (TH-13) : une connexion SQLite partagée entre threads aurait rendu l'application quasiment indisponible sous tout serveur WSGI multi-thread. Récupération après coupure brutale du processus vérifiée pour le mode WAL de SQLite. Aucun autre composant à panne testable n'existe encore (pas de file de messages, pas de cache, pas de service externe réel).

## 17. Limitations connues

- Fondation SQLite/stdlib, pas prête pour une charge de production (voir `production-readiness.md`).
- Répondeur conversationnel non génératif (3 accusés de réception fixes pour GREEN) — décision explicite, pas un défaut caché.
- Modèle d'émotion entraîné sur des commentaires Reddit en anglais, registre différent d'une conversation thérapeutique en français ; observabilité uniquement, jamais décisionnel.
- Pas d'infrastructure de déploiement réelle : le registre de modèles ne fait que suivre un état.
- Pas de console d'administration complète (rôles/permissions fines, feature flags).
- Pas d'E2E navigateur automatisé (Playwright ou équivalent non ajouté, décision laissée à l'utilisateur).

## 18. Risques restants

Voir `docs/security/threat-model.md` Section « Dette de vérification assumée » pour la liste complète tracée. Les plus importants : reprise de notifications réduite mais pas totalement fermée (TM-08 — un worker de backoff avec lettre morte existe désormais, `scripts/retry_notifications.py`, mais le cas d'une panne de processus entre l'écriture `PENDING` et la mise à jour finale reste ouvert), absence de test d'intrusion externe, absence de validation clinique de toute nature.

## 19. Procédure de déploiement

Aucune procédure de déploiement de production n'existe (aucune infrastructure cible choisie). Procédure de développement local : `docs/deployment/local-development.md`. Écart à combler avant un vrai déploiement : `docs/deployment/production-readiness.md`.

## 20. Sauvegarde et restauration

**Non configuré.** SQLite de développement n'a aucune sauvegarde automatisée. Une restauration testée en conditions réelles est listée comme obligatoire, pas optionnelle, dans `production-readiness.md`.

## 21. Monitoring

**Non configuré au-delà de la journalisation structurée locale** (`request_id`, actions d'audit, jamais de contenu clinique — voir threat model TH-09). Aucune métrique, trace, ni tableau de bord opérationnel. Listé dans `production-readiness.md`.

## 22. Rollback

Voir `docs/deployment/rollback.md` : code (Git), schéma de base de données (manuel, limite assumée), modèle d'IA déployé (automatisé et testé, `POST .../rollback`), politique clinique (Git + rechargement au démarrage).

## 23. Runbook opérationnel

Voir `docs/deployment/runbook.md` : alerte ROUGE non prise en compte, disque plein (incident réel rencontré pendant ce projet), échec de suite de tests, suspicion de fuite de secret, rollback de modèle en urgence, latence anormale.

## 24. Améliorations futures

Par ordre de dépendance logique, pas de priorité imposée : (1) intégration LLM réelle avec pipeline de sécurité complet (Section 7 du prompt maître) si décidé par l'utilisateur ; (2) infrastructure de déploiement réelle (PostgreSQL, secrets, TLS, monitoring) ; (3) fermer le cas résiduel de TM-08 (réclamation par verrouillage optimiste des lignes `PENDING` orphelines) et planifier réellement `scripts/retry_notifications.py` en production ; (4) console d'administration complète ; (5) E2E navigateur automatisé ; (6) test de charge réel et test d'intrusion externe ; (7) adoption d'Argon2id si une dépendance crypto approuvée devient disponible (voir ADR-003).

## 25. Dépendances de validation clinique

Aucune fonctionnalité de ce projet ne doit être présentée comme cliniquement validée. Avant tout pilote avec de vrais patients, au minimum : revue par un psychologue clinicien des seuils de `crisis-policy-v1.json` et des textes de `response-templates-v1.json` (actuellement `approved_by`/`approved_at` à `null`, ce qui bloque déjà techniquement leur usage hors développement) ; validation par un comité d'éthique ; définition des contacts d'urgence réels par juridiction ; et, si l'étude contrôlée randomisée décrite dans le document de conception source est poursuivie, un comité de surveillance (psychiatre, psychologue clinicien, éthicien IA, biostatisticien) conformément à ce document.

## 26. Recommandation de sortie

**PASS WITH WARNINGS**, cohérent avec le statut de chaque rapport de phase individuel. La fondation est solide, testée honnêtement, et documente ses propres limites sans les dissimuler. Elle n'est **pas recommandée** pour un déploiement avec de vrais patients en l'état : `production-readiness.md` et `Section 25` ci-dessus listent des conditions préalables non négociables, pas des suggestions.
