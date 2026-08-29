# PHASE REPORT

Phase : 0 (V2) — Audit du dépôt existant face au Prompt Maître « Psychologue Intelligent V2 »
Date : 2026-08-28
Auteur : agent code
Objectif : Établir l'état réel du dépôt, le confronter à l'architecture cible du prompt V2, mesurer l'écart, proposer une roadmap, des critères d'acceptation, un registre de risques et une stratégie de migration — **avant toute implémentation** (règle 151 du prompt maître).

> Ce rapport ne remplace pas [`docs/reports/phase-0-audit.md`](phase-0-audit.md) (l'audit d'origine, dépôt vide, 2026-08-24). Il le complète : le dépôt n'est plus vide, et la cible a changé d'échelle.

---

## 1. Résumé exécutif

Le dépôt contient une **fondation logicielle réelle, testée et documentée honnêtement** (~2 260 lignes applicatives, ~2 600 lignes de tests, 95 tests, 93 % de couverture, 18 rapports de phase, 5 ADR, threat model, audit de sécurité). Cette fondation a été construite sous une contrainte explicite — **ADR-003 : zéro dépendance runtime** — qui a produit : un serveur WSGI en bibliothèque standard, SQLite, trois frontends HTML/CSS/JS vanilla, un moteur de crise indépendant du LLM, un pipeline d'apprentissage continu avec double approbation, et (ADR-005, premier écart assumé à ADR-003) un répondeur génératif auto-hébergé `llama-cpp-python` pour les seules réponses GREEN.

Le **Prompt Maître V2 demande une plateforme d'une autre catégorie** : Next.js 16 / React 19, FastAPI, PostgreSQL + pgvector, Redis, RabbitMQ, PyTorch / vLLM / Triton, STT/TTS temps réel + WebRTC, MLflow, OpenTelemetry, multi-tenancy, 23 phases, gouvernance clinique formelle. **Aucun composant de la stack cible n'est présent aujourd'hui.**

**L'écart n'est pas incrémental : c'est une reconstruction quasi complète de l'infrastructure et des interfaces**, dans laquelle la valeur à préserver est le **cœur métier et les invariants de sûreté** (moteur de crise, politiques versionnées, pipeline d'apprentissage gouverné, threat model, jeux de tests), pas le code de transport ni le stockage.

**Conclusion procédurale : l'implémentation ne doit pas démarrer avant décision de l'utilisateur** sur trois points structurants (Section 11). Ce sont des choix de produit, de budget et de gouvernance, pas des choix techniques que l'agent peut trancher seul.

STATUS : **AUDIT COMPLETE — AWAITING DECISIONS**

---

## 2. Méthode d'audit

- Lecture de l'intégralité du code applicatif (`backend/app/*.py`), des tests (`tests/*.py`), des trois frontends, des scripts, de la CI, des fichiers de configuration et de déploiement.
- Lecture des 18 rapports de phase, des 5 ADR, du modèle de données, du threat model, du rapport d'audit de sécurité et du rapport final.
- Confrontation systématique de chaque section du Prompt Maître V2 (points 3 à 150) à l'existant.
- Aucun fichier applicatif créé ou modifié. Seul ce rapport est ajouté.

---

## 3. Architecture actuelle (constatée, pas déclarée)

### 3.1 Vue d'ensemble

Monolithe modulaire **API-first en WSGI**, une origine unique sert l'API JSON et trois SPA statiques.

```text
frontend/           3 apps HTML/CSS/JS vanilla (patient, clinician, admin) — pas de build, pas de framework
  app.js  46 loc    patient : register/login/onboarding/chat/profil/suppression
  clinician/app.js  253 loc   dashboard, timeline patient, alertes, revue feedback/modèles
  admin/app.js      268 loc   utilisateurs, relations patient-clinicien, learning
        │  fetch JSON, jeton Bearer en sessionStorage
        ▼
backend/app/http.py  324 loc   routeur WSGI unique, ~40 routes, rate limiting en mémoire,
                                en-têtes de sécurité, RFC 9457, une connexion SQLite par requête
        ▼
backend/app/  (domaine — 1 fichier par domaine, style terse mono-ligne assumé)
  auth.py 164        inscription, login, MFA TOTP (HMAC maison), sessions opaques, profils, consentements, PHQ-9 wiring
  security.py 56     PBKDF2-HMAC-SHA256 600k, comparaison constante, hachage jetons
  phq9.py 17         scoring PHQ-9 (item 9 isolé)
  crisis.py 96       CrisisDetector : règles versionnées + RiskModel (port), combinaison conservatrice, UNKNOWN→ORANGE
  ai.py 64           ports : LLMProvider, RiskModel ; KeywordRiskModel, TemplatedSupportiveResponder
  policy.py 141      chargement + validation des politiques JSON (crise, règles, templates) au boot
  pipeline.py 84     handle_incoming_message : risque→crise→persistance→alerte→notification, transactionnel
  alerts.py 30       cycle de vie d'alerte, clé d'idempotence
  notifications.py 162  LogNotificationProvider, statut de livraison, retry/backoff, dead-letter
  conversation.py 121   conversation active unique/patient, séquençage messages, consentement CARE requis
  responder.py 22    compose_reply : ORANGE/RED → templates fixes ; GREEN → llm.generate(context)
  personalization.py 85  build_context best-effort (prénom, about_me, bande PHQ-9 qualitative, 6 derniers messages)
  emotion.py 76      TfidfLogisticEmotionModel — inférence Python pure depuis poids JSON, observabilité seule
  local_llm.py 144   LocalGenerativeResponder — llama-cpp-python importé en différé, verrou global, fallback templated
  clinician.py 143   relations patient-clinicien, timeline, actions d'alerte, revue
  learning.py 240    échantillonnage consenti, anonymisation regex, human_feedback, datasets, model_versions, 2 approbations, deploy/rollback
  admin.py 38        listes utilisateurs / relations
  db.py 198          11 migrations SQL additives, connect() (WAL, FK on), migrate() idempotent
  config.py 44       Settings depuis variables d'environnement PI_*
        ▼
SQLite (fichier), mode WAL, une connexion par requête
```

### 3.2 Stack réelle

| Couche | Présent | Cible V2 | Statut |
| --- | --- | --- | --- |
| Frontend | HTML/CSS/JS vanilla, 3 SPA, pas de build | Next.js 16, React 19.2, TS, Tailwind, shadcn/ui, TanStack Query, Zod, RHF | **absent** |
| API | WSGI maison (`http.py`), routeur `if/elif` | FastAPI, Pydantic v2, OpenAPI généré, WebSockets | **absent** (OpenAPI existe mais écrit à la main) |
| Langage backend | Python 3.12, **stdlib seule au runtime** | Python 3.12+, stack complète | partiel |
| DB | SQLite, migrations SQL maison | PostgreSQL + pgvector (+ PostGIS si besoin), Alembic, asyncpg, SQLAlchemy 2 | **absent** |
| Cache / temps réel | rate limiting `deque` en mémoire | Redis (cache, sessions, presence, locks, state) | **absent** |
| Messaging | worker de retry lancé à la main (`scripts/retry_notifications.py`) | RabbitMQ (+ Celery si valeur) | **absent** |
| LLM | `llama-cpp-python` CPU, un modèle Qwen2.5-1.5B, ADR-005 | abstraction multi-fournisseur (OpenAI/Anthropic/local/compatible), FAST/STANDARD/DEEP, vLLM/Triton | partiel (1 provider local, pas d'abstraction multi) |
| STT / TTS / Voix | **rien** | Whisper/STT compatible, TTS multi, VAD, WebRTC, barge-in, VoiceSessionManager | **absent** |
| ML | inférence Python pure ; `scikit-learn` en extra entraînement | PyTorch, Transformers, Datasets, PEFT, Accelerate, ONNX Runtime | **absent** |
| Model registry | table `model_versions` + états, pas d'artefacts | MLflow (experiments, lineage, aliases, promotion, rollback) | partiel (état seul) |
| Observabilité | logs structurés (`request_id`), pas de métriques/traces | OpenTelemetry, Prometheus, Grafana, Loki, Tempo/Jaeger | **absent** |
| Auth | sessions opaques, MFA TOTP maison, PBKDF2 (pas Argon2id) | idem esprit, mais à réimplémenter sur la nouvelle stack | partiel |
| Multi-tenancy | aucune notion d'organisation/clinique | Organization → Clinic → Clinician → Patient, isolation | **absent** |
| Déploiement | Railway (NIXPACKS), 1 conteneur, SQLite sur volume | Docker Compose (dev), K8s/Helm (échelle) | partiel (démo Railway) |
| CI | GitHub Actions : ruff, mypy, tests, coverage 85 %, bandit, pip-audit, scan secrets, OpenAPI | + typecheck front, E2E, AI eval, perf gates, container scan, DAST, Semgrep | partiel |
| Tests | 95 tests unittest, 93 % ; pas d'E2E navigateur | Unit/Integration/Contract/E2E/Security/Perf/AI-Safety/Voice/Resilience/Regression | partiel (bon socle, plusieurs catégories absentes) |

### 3.3 Ce qui est déjà bon et doit être préservé

Ce sont les actifs qui justifient une **migration** plutôt qu'un greenfield « from zero » :

1. **Invariants de sûreté formalisés et testés** (`docs/architecture/overview.md` §Invariants, `crisis.py`, `responder.py`) : le LLM ne décide jamais d'une crise ; ORANGE/RED contournent structurellement le répondeur ; test-espion de régression `test_generative_responder.py`.
2. **Moteur de crise indépendant, fail-safe** : dégradation conservatrice quand le RiskModel échoue, `UNKNOWN`→ORANGE, versions de politique/règles/modèle attachées à chaque décision.
3. **Politiques cliniques hors code, versionnées, bloquées si non approuvées** (`approved_by: null` empêche l'usage hors dev) — ADR-002.
4. **Pipeline d'apprentissage gouverné** : consentement LEARNING séparé et révocable, échantillonnage limité aux consentants, anonymisation puis revue humaine (jamais l'inverse), datasets immuables, **2 approbations distinctes** avant déploiement, rollback testé.
5. **Threat model synchronisé au code** (13 menaces STRIDE/OWASP, chacune tracée à un test réel) + rapport d'audit de sécurité (3 vulnérabilités réelles trouvées, reproduites, corrigées à la racine, test de régression permanent — dont une race condition contournant l'invariant « un rejet clinique bloque un modèle »).
6. **Modèle de données clinique** (`docs/architecture/data-model.md`, 11 migrations) : schéma d'alertes, crise, notifications, consentements, feedback, registry — transposable quasi tel quel vers PostgreSQL.
7. **Jeux de tests adversariaux et E2E** (`test_security.py` 472 loc, `test_e2e_journeys.py` 330 loc, `test_crisis_pipeline.py` 265 loc) : la logique de test se réécrit sur la nouvelle stack, mais les **scénarios** sont un actif.
8. **Culture de rapport et d'ADR** : chaque décision est tracée, chaque limite est déclarée et non dissimulée. Le prompt V2 (règles 123–125) demande exactement cela.

### 3.4 Dette technique et limites déjà déclarées par le projet

Reprises de `final-report.md` §17–18, `production-readiness.md`, threat model §« dette de vérification » :

- SQLite + rate limiting mémoire : non admissibles multi-instance.
- PBKDF2 au lieu d'Argon2id (écart ADR-003 assumé).
- Répondeur génératif : latence CPU **30 s à > 1 min** mesurée sur Railway ; appels sérialisés (verrou global) ; **aucune revue humaine du contenu généré menée**.
- Modèle d'émotion entraîné sur commentaires Reddit anglais — registre éloigné d'une conversation thérapeutique française ; observabilité seule.
- Aucun canal de notification réel (email/SMS/push) ; `LogNotificationProvider` seulement.
- Aucune infrastructure de production, aucun secret manager, aucun monitoring, aucune sauvegarde automatisée, aucune restauration testée.
- Aucun test de charge réel, aucun test d'intrusion externe.
- **Aucune validation clinique d'aucune sorte** : aucun psychologue, psychiatre ou éthicien n'a examiné le système ; aucune donnée patient réelle n'a transité.
- Cas résiduel TM-08 ouvert : panne de processus entre l'écriture `PENDING` d'une notification et sa mise à jour finale.
- Rollback de schéma DB : manuel.

---

## 4. Architecture cible (Prompt Maître V2)

Reformulée depuis les sections 1, 3–13, 16–26, 42–43, 66–73, 93–94 du prompt :

```text
                         ┌─────────────────────────────────────────┐
  Patient / Clinicien /  │  Next.js 16 (App Router, RSC, streaming) │
  Chercheur / Admin  ───▶│  + WebRTC (média voix) + WS (events)     │
                         └───────────────┬─────────────────────────┘
                                         ▼
                         ┌─────────────────────────────────────────┐
                         │  FastAPI (REST /api/v1/* + /ws/*)        │
                         │  Application Services → Domain → Infra   │
                         └───────────────┬─────────────────────────┘
        ┌────────────────────────────────┼───────────────────────────────────┐
        ▼                                ▼                                   ▼
 ConversationOrchestrator        SafetyEngine (indépendant LLM)       VoiceSessionManager
  ├ ContextBuilder                ├ RiskClassifier                     ├ VAD → streaming STT
  ├ PersonalizationEngine         ├ CrisisDetector                     ├ streaming TTS
  ├ MemoryService (4 niveaux)     ├ RuleEngine / PolicyEngine          └ barge-in / reconnect
  ├ DialoguePolicy (FAST/DEEP)    └ EscalationEngine
  └ ModelRouter → LLMProvider(s)         │
        │                                ▼
        ▼                        AlertEngine → NotificationService (Email/SMS/Push adapters)
  OutputSafety (PII, hallucination, policy, crisis-consistency)
        │
        ▼
 ┌──────────────┬───────────┬───────────┬──────────────┬────────────────────┐
 │ PostgreSQL   │ pgvector  │  Redis    │  RabbitMQ    │  Object storage    │
 │ (source of   │ (mémoire  │ (cache,   │ (embeddings, │  (audio, artefacts)│
 │  vérité)     │ sémant.,  │  presence,│  summaries,  │                    │
 │              │  RAG)     │  locks)   │  analytics)  │                    │
 └──────────────┴───────────┴───────────┴──────────────┴────────────────────┘
        │
        ▼  (hors chemin critique)
 Events → Analytics → Clinical Monitoring → Human Feedback → Learning Pipeline
        → Offline/Safety/Clinical Eval → MLflow Registry (SHADOW→CANARY→PROD) → Rollback

 Transverse : OpenTelemetry (traces/métriques/logs) · RBAC 8 rôles · multi-tenant
              Organization→Clinic→Clinician→Patient · consentement versionné ·
              audit sans contenu clinique · feature flags · i18n fr/en
```

Invariants cibles (identiques en esprit à l'existant, à re-garantir sur la nouvelle stack) : sections 2, 25, 28, 30, 60–62 du prompt.

---

## 5. Analyse d'écart (gap analysis)

| # | Domaine | Existant | Cible V2 | Écart | Effort* |
| --- | --- | --- | --- | --- | --- |
| G-01 | Frontend | 3 SPA vanilla | Next.js/React/TS + design system original | Réécriture totale | XL |
| G-02 | API | WSGI maison | FastAPI + Pydantic v2 + couches App/Domain/Infra | Réécriture transport, portage domaine | L |
| G-03 | DB | SQLite | PostgreSQL + Alembic + pgvector | Migration schéma + réécriture accès données | L |
| G-04 | Cache/état | mémoire | Redis | Nouveau | M |
| G-05 | Messaging | script manuel | RabbitMQ + workers | Nouveau | M |
| G-06 | Conversation | send_message linéaire | ConversationOrchestrator, DialogueState, FAST/DEEP, streaming | Refonte + extension | L |
| G-07 | Mémoire | `build_context` best-effort, 6 messages | MemoryService 4 niveaux, embeddings, retrieval pgvector, consent/révocation/oubli | Nouveau, substantiel | XL |
| G-08 | Personnalisation | prénom + about_me + bande PHQ-9 | PersonalizationEngine (ton, longueur, directivité, style, objectifs) + UserProfile étendu | Extension forte | L |
| G-09 | Safety | CrisisDetector + règles | SafetyEngine complet (RiskClassifier, CrisisDetector, Rule/PolicyEngine, EscalationEngine) + OutputSafety + défense prompt injection | Extension + durcissement | L |
| G-10 | Modèles IA | 1 responder local + 1 émotion | LLM multi-fournisseur, Emotion/Risk/Crisis/Embedding/STT/TTS distincts, ModelRouter | Nouveau, substantiel | XL |
| G-11 | Voix | absent | STT/TTS streaming, VAD, WebRTC, barge-in, VoiceSessionManager, UX états, privacy audio | Nouveau, substantiel | XL |
| G-12 | Dashboard clinicien | listes fonctionnelles | Patient 360, Alert Center, AI Review Center, feedback structuré, perf dashboard, AI quality dashboard | Extension forte | L |
| G-13 | Résumé clinique IA | absent | PatientSummaryService + Evidence (traçabilité de chaque affirmation) | Nouveau | M |
| G-14 | MLOps | table d'états | MLflow, environnements EXPERIMENTAL→RETIRED, shadow/canary, data quality gates, dataset versioning (DVC) | Nouveau, substantiel | XL |
| G-15 | Apprentissage continu | pipeline gouverné (socle) | idem + eval offline/safety/clinique automatisée, model cards générés | Extension | M |
| G-16 | Observabilité | logs | OTel + Prometheus + Grafana + Loki + Tempo, dashboards latence/perf, corrélation multi-id | Nouveau | L |
| G-17 | Résilience | 1 bug concurrence corrigé | fault injection systématique (DB/Redis/MQ/LLM/STT/TTS/notif/réseau/GPU), modes dégradés | Nouveau | M |
| G-18 | Sécurité | threat model + audit OWASP/STRIDE | + OWASP LLM/GenAI, NIST AI RMF GenAI profile, AI red team suite, DAST, container scan, pentest externe | Extension | L |
| G-19 | Multi-tenancy | aucune | Organization/Clinic isolation, tests fuite tenant | Nouveau, transverse | L |
| G-20 | Perf | benchmark ponctuel | cibles latence (TTFT/TTFA/TTLT…), k6/Locust, load test voix, précalcul post-conversation | Nouveau | M |
| G-21 | Gouvernance clinique | ADR + avertissements | comité (psychiatre/psy/éthique/biostat), oversight policy, plan d'éval clinique, support étude RCT | **Non logiciel** — dépend de l'utilisateur | — |
| G-22 | Conformité | avertissements honnêtes | PIA, doc technique AI Act, human oversight, gestion d'incident, data/model governance | Extension + juridique | L |
| G-23 | i18n | tout en français, en dur | i18n fr/en dès l'architecture + identification de langue vocale + éval variantes (fr/en camerounais, code-switching) | Nouveau | M |

\* Échelle relative S/M/L/XL — pas une estimation calendaire. La somme représente un effort pluri-mensuel pour une équipe.

---

## 6. Contradictions et points à arbitrer

1. **ADR-003 (zéro dépendance runtime) est incompatible avec la cible V2.** Le prompt V2 impose une stack lourde. Il faut soit **remplacer formellement ADR-003** par un nouvel ADR (« adoption stack pilote »), soit documenter chaque brique comme écart. Recommandation : nouvel ADR-006 qui acte le changement de contexte (on n'est plus dans un environnement sans réseau) et supersede ADR-003.
2. **Le prompt V2 dit « n'utilise pas Triton / K8s juste pour faire moderne »** (règles 10, 93) mais **liste une stack maximale par ailleurs.** Interprétation retenue : la stack cœur (Next.js, FastAPI, Postgres+pgvector, Redis, RabbitMQ, MLflow, OTel) est attendue ; vLLM/Triton/K8s/DVC sont **conditionnels** à un besoin démontré. À valider.
3. **Le répondeur génératif actuel (Qwen 1.5B CPU, latence 30–60 s)** est incompatible avec les cibles de latence V2 (§14 : premier token < 1–2 s). Il faut soit GPU/hébergement dédié, soit une API externe (Claude/OpenAI) — ce qui réintroduit le transfert de données patient hors système, explicitement écarté en ADR-005. **Décision produit + budget requise.**
4. **Voix temps réel (WebRTC + STT/TTS)** implique un coût d'infrastructure récurrent (GPU ou API STT/TTS) et une surface de conformité nouvelle (audio = donnée biométrique potentielle). Doit être priorisé explicitement, pas supposé.
5. **Multi-tenancy** : le prompt demande de « concevoir dès le début » pour plusieurs organisations (règle 69). Cela impacte **chaque table et chaque requête**. Le faire maintenant (pendant la migration) coûte beaucoup moins cher qu'après. Recommandation : l'inclure dès la Phase 2.
6. **Validation clinique** (règles 98–99, 148) : le logiciel peut *préparer* le terrain (modules d'étude, traçabilité, oversight), mais **rien ne peut être déclaré cliniquement validé** sans comité réel. Ce n'est pas un blocage à l'implémentation, mais un blocage au déploiement avec de vrais patients — à répéter dans chaque rapport.

---

## 7. Stratégie de migration recommandée

**Principe : strangler pattern, cœur de sûreté d'abord, pas de big-bang.**

- **Ne pas supprimer** le code existant tant que son remplacement n'est pas testé au moins à parité (règle 128). Le déploiement Railway actuel reste la « démo v1 » jusqu'à ce qu'une v2 la dépasse.
- **Phase A — Socle stack (nouveau, en parallèle)** : monter FastAPI + PostgreSQL + Alembic + Redis + RabbitMQ + Docker Compose + OTel + CI étendue, sans encore porter de métier. Porter le schéma des 11 migrations SQLite vers Alembic/PostgreSQL (1:1, en ajoutant `organization_id` partout — multi-tenant dès le départ).
- **Phase B — Portage du cœur de sûreté** : `crisis.py`, `policy.py`, `pipeline.py`, `alerts.py`, `responder.py` vers la couche Domain, avec les **mêmes tests** (réécrits pour pytest + DB Postgres). Objectif : les invariants de `overview.md` §Invariants sont re-garantis et re-testés sur la nouvelle stack **avant** d'ajouter des fonctionnalités.
- **Phase C — Portage identité / consentement / PHQ-9 / conversation / clinicien / learning** module par module, chacun avec sa suite de tests portée, l'ancien endpoint WSGI retiré seulement quand le nouveau passe.
- **Phase D — Frontend** : nouveau projet Next.js, design system original d'abord (Phase 1 du prompt), puis app patient, puis clinicien, puis admin. Les SPA vanilla restent servies jusqu'au basculement écran par écran.
- **Phase E et au-delà** : fonctionnalités nouvelles du prompt V2 (MemoryService, PersonalizationEngine étendu, SafetyEngine complet, Voix, Patient 360, MLOps, etc.) selon la roadmap Section 8.
- **Données** : aucune donnée patient réelle n'existe → **pas de migration de données**, seulement de schéma. C'est un avantage majeur : la migration est sans risque pour des personnes réelles.

---

## 8. Roadmap proposée (mappée sur les phases du prompt V2)

| Phase prompt | Contenu | Gate de sortie | Dépend de |
| --- | --- | --- | --- |
| **0 (ce rapport)** | Audit + décisions | Décisions utilisateur prises (Section 11) | — |
| 1 | Architecture détaillée + design system Next.js (tokens, composants, états) + ADR-006 (stack) + threat model V2 (OWASP LLM + NIST AI RMF) | Design system revu, ADR actés, threat model étendu | 0 |
| 2 | Fondation : FastAPI, PostgreSQL+Alembic, Redis, RabbitMQ, config, logging OTel, auth+RBAC (8 rôles), audit, health, CI étendue, Docker Compose, **multi-tenant dès ici** | Tests fondation + scans passent ; `docker compose up` fonctionne | 1 |
| 3 | Plateforme utilisateur : inscription, login, MFA, consentement versionné, profil étendu, onboarding, confidentialité, suppression de compte | E2E parcours + contrôles d'accès (BOLA/IDOR, cross-tenant) passent | 2 |
| 4 | Moteur de conversation : Conversation, messages, streaming SSE/WS, DialogueState, ConversationOrchestrator, FAST/DEEP path | Tests conversation + streaming + interruption texte passent | 3 |
| 5 | Moteur de mémoire : working/episodic/semantic/longitudinal, embeddings, retrieval pgvector, oubli, révocation | Tests retrieval (pertinence, périmés, supprimés, révoqués, conflits) passent | 4 |
| 6 | Personnalisation : préférences, style, longueur, fréquence de questions, objectifs, langue ; tests « même message + profil différent » et « user différent + même condition critique » | Tests personnalisation + cohérence sécurité passent | 5 |
| 7 | Safety engine : RiskClassifier, CrisisDetector, Rule/PolicyEngine, EscalationEngine, OutputSafety (PII/hallucination/policy/crisis-consistency), défense prompt injection, SAFE_FALLBACK | Simulations crise + défaillances + AI red team (injection/jailbreak/extraction/poisoning) passent | 6 |
| 8 | PHQ-9 / assessment : instrument versionné, scoring, historique, tendance, rappels, contrôle d'accès | Cas critiques couverts à 100 % | 3 |
| 9 | Risque / crise / alertes : niveaux GREEN/ORANGE/RED, cycle de vie, SLA, escalade, accusé, résolution, seuils configurables/versionnés/audités | Cycle de vie d'alerte + SLA + audit de chaque transition passent | 7 |
| 10 | Alertes + NotificationService : adapters Email/SMS/Push, retry/backoff/dedup/idempotence/fallback/tracking, outbox transactionnelle (ferme TM-08) | Tests panne/réessai + idempotence passent | 9 |
| 11 | Voix temps réel : STT/TTS abstraits, VAD, streaming, WebRTC + fallback WS, barge-in, reconnexion, états UI, privacy audio (consentement, rétention configurable, suppression) | Tests voix (accents, bruit, silence, interruption, perte paquet, reconnect, micro refusé, langue mixte) + charge voix passent | 4 |
| 12 | Dashboard clinicien : Today's Overview, Patient List, Alert Center, AI Review, Analytics | RBAC + accessibilité (WCAG) + tests ergonomie passent | 9 |
| 13 | Patient 360 + PatientSummaryService + Evidence (traçabilité) | Chaque affirmation du résumé reliée à sa source, vérifié par test | 12 |
| 14 | Clinician AI Review : APPROVE/EDIT/REJECT/FLAG, évaluation structurée 1–5, feedback structuré (catégories), perf dashboard clinicien | Tests feedback + non-usage punitif documenté | 12 |
| 15 | Analytics produit + clinique/IA, séparés et gouvernés ; AI quality dashboard ; AI cost control + ModelRouter | Séparation des deux catégories vérifiée ; routing testé | 13, 14 |
| 16 | Apprentissage continu : sampling→privacy→anonymisation→revue→dataset versionné→training→eval offline/safety/clinique→shadow→canary→prod, révocable | Tests révocation, anonymisation, approbation, rollback passent | 14 |
| 17 | MLOps : MLflow (experiments/lineage/aliases/promotion), environnements, data quality gates, model cards générés, dataset versioning | Pipeline experiment→deploy→rollback E2E passe | 16 |
| 18 | Durcissement sécurité : audit complet (app/API/DB/infra/identité/LLM/mémoire/voix/notif/ML/CI), AI red team suite complète, DAST, container scan, dependency/secret scan | Aucune vulnérabilité critique ouverte ; élevées décidées formellement | tout |
| 19 | Performance : mesure avant/après sur API/DB/Redis/LLM/STT/TTS/WS/WebRTC/frontend, cibles §14, k6/Locust, précalcul post-conversation | Cibles mesurées et rapportées (pas garanties) | tout |
| 20 | Résilience : fault injection DB/Redis/MQ/LLM/STT/TTS/notif/réseau/GPU, modes dégradés, mode offline UX | Fallbacks vérifiés pour chaque panne | tout |
| 21 | Préparation étude clinique : participants, consentement, randomisation, groupes, visites, évaluations, adhérence, événements indésirables, exports — **sans jamais déclarer l'étude valide** | Modules présents ; gouvernance clinique documentée (comité réel = hors logiciel) | 15 |
| 22 | Validation complète : 8 scénarios E2E obligatoires (A–H du prompt §145), gates sécurité/IA/clinique finaux, rapports (model card, threat model, pentest, AI red team, dependency, secrets) | Tous les scénarios E2E + tous les gates passent | tout |
| 23 | Release candidate : release notes, runbooks, rollback, rapport final ; checklist §150 | Approbations techniques ET cliniques (ces dernières = hors périmètre agent) | 22 |

Chaque phase produit : code fonctionnel + tests + doc + analyse sécurité + analyse perf + PHASE REPORT (règles 123, 127). Aucune phase ne passe la gate si un critère critique échoue.

---

## 9. Critères d'acceptation (transverses, applicables à chaque phase)

Une fonctionnalité est `DONE` uniquement si : implémentée + intégrée + testée + sécurisée + observée + documentée + validée (règle 151).

- [ ] Code lint + typecheck propres (ruff/mypy back, eslint/tsc front).
- [ ] Tests unitaires + intégration verts ; couverture backend ≥ 85 % (seuil actuel, à maintenir).
- [ ] Aucune régression sur les **invariants de sûreté** (`overview.md` §Invariants) — test dédié par invariant.
- [ ] Aucune donnée clinique dans les logs techniques (test de fuite PII/PHI).
- [ ] Contrôle d'accès : tests négatifs BOLA/IDOR, cross-patient, cross-clinician, cross-tenant.
- [ ] Scans sécurité : bandit, pip-audit/npm audit, semgrep, gitleaks, trivy — 0 critique.
- [ ] Endpoint documenté dans OpenAPI (généré par FastAPI), erreurs RFC 9457, pas de stack trace exposée.
- [ ] Traçabilité : `request_id`/`session_id`/`conversation_id`/`message_id` propagés (OTel).
- [ ] PHASE REPORT généré selon le template règle 123.
- [ ] Limites et risques résiduels déclarés explicitement, jamais dissimulés.
- [ ] Aucune donnée patient réelle utilisée ; aucun `mock` en environnement non-démo (règle 122).

---

## 10. Registre de risques

| ID | Risque | Impact | Prob. | Mitigation | Vérification |
| --- | --- | --- | --- | --- | --- |
| R-01 | La migration casse un invariant de sûreté sans être détectée | Critique | Moyenne | Porter les tests d'invariant **avant** le code ; Phase B dédiée ; test-espion crise conservé | Suite crise + `test_generative_responder` portées et vertes |
| R-02 | Scope V2 dépasse la capacité réelle → plateforme à moitié finie (ce que le prompt interdit, règle 150) | Élevé | Élevée | Roadmap par gates ; aucune phase « à moitié » ; priorisation explicite avec l'utilisateur | Gate de chaque phase |
| R-03 | Latence LLM incompatible avec cibles §14 sans GPU/API externe | Élevé | Élevée | Décision produit Section 11 ; ModelRouter FAST/DEEP ; cibles = objectifs mesurés, pas garanties | Benchmarks Phase 19 |
| R-04 | Intégration LLM génératif rouvre TH-04 (prompt injection) à pleine surface | Critique | Élevée | OutputSafety obligatoire ; RAG/mémoire traités comme données jamais instructions ; AI red team suite ; rayon d'impact borné (crise décidée avant/hors LLM) | AI red team Phase 7 + 18 |
| R-05 | Fuite inter-tenant après ajout multi-tenancy | Critique | Moyenne | `organization_id` dans chaque table + chaque requête ; middleware de scoping ; tests fuite tenant systématiques | Tests cross-tenant chaque phase |
| R-06 | Voix : audio brut conservé trop longtemps / traité comme biométrie sans base légale | Critique | Moyenne | Consentement micro explicite, rétention configurable courte par défaut, suppression, chiffrement, traitement local si possible | Tests privacy voix Phase 11 + PIA Phase 22 |
| R-07 | pgvector / mémoire sémantique réinjecte une mémoire supprimée ou révoquée | Critique | Moyenne | Statut de mémoire (`ACTIVE/REVOKED/EXPIRED`), filtre au retrieval, propagation de suppression | Tests mémoire Phase 5 |
| R-08 | MLflow / pipeline d'apprentissage entraîne sur données non consenties ou ré-identifiables | Critique | Moyenne | Consentement LEARNING vérifié au sampling ; anonymisation + revue humaine ; datasets immuables ; 2 approbations | Tests révocation/anonymisation Phase 16 |
| R-09 | Seuils cliniques (`crisis-policy`) présentés comme décisions médicales | Critique | Moyenne | Politiques versionnées, `approved_by` bloquant hors dev, avertissements UX, comité clinique réel avant pilote | Tests version/rollback + gate clinique Phase 22 |
| R-10 | Coût d'infrastructure (GPU, Redis, MQ, STT/TTS, monitoring) non budgété | Élevé | Moyenne | Chiffrage avant Phase 2 ; AI cost control (§105) dès Phase 15 ; commencer sans GPU si possible | Décision Section 11 |
| R-11 | Conformité AI Act / RGPD mal qualifiée (produit santé mentale = potentiellement haut risque) | Élevé | Moyenne | PIA, doc technique, human oversight ; qualification juridique par conseil spécialisé (hors agent) | Gate conformité Phase 22 |
| R-12 | Perte de l'honnêteté documentaire actuelle sous la pression du scope | Moyen | Moyenne | Template PHASE REPORT imposé ; section « limites/risques résiduels » obligatoire ; le code et ses tests font foi | Revue de chaque rapport |
| R-13 | Environnement de dev Windows : certaines briques (vLLM, Triton, llama.cpp GPU) mal supportées | Moyen | Élevée | Docker Compose pour tout le stack ; dev dans conteneurs Linux ; CI Linux | `docker compose up` Phase 2 |

---

## 11. Décisions requises de l'utilisateur avant implémentation

L'agent **ne commencera pas la Phase 1** avant réponse sur ces points. Ce ne sont pas des détails techniques — ils déterminent des mois de travail, un budget d'infrastructure et un périmètre de gouvernance.

### D-1 — Portée et rythme
Le Prompt V2 décrit 23 phases représentant un effort pluri-mensuel. Options :
- **(a)** Migration + cœur de sûreté d'abord (Phases 0→2→B→3→7→9), stack complète mais fonctionnalités avancées différées. *Livre une base V2 saine en quelques semaines.*
- **(b)** Suivre la roadmap Section 8 phase par phase, dans l'ordre, jusqu'à RC. *Le plus fidèle au prompt, le plus long.*
- **(c)** Cibler un sous-ensemble précis (ex. « conversation + mémoire + personnalisation + voix », sans MLOps complet ni étude clinique pour l'instant).

### D-2 — Stratégie LLM et budget
Les cibles de latence V2 (§14) sont inatteignables avec le modèle CPU actuel. Options :
- **(a)** API externe (Claude/OpenAI) pour le chemin STANDARD/DEEP → **le contenu des messages patient sort du système** (revient sur ADR-005). Rapide, coût à l'usage.
- **(b)** Hébergement GPU dédié pour vLLM → données restent internes, coût fixe mensuel significatif.
- **(c)** Hybride : petit modèle local pour FAST path, API externe pour DEEP, avec consentement explicite du patient au transfert.
- **(d)** Rester CPU local et **assumer/documenter** que les cibles §14 ne sont pas tenues pour l'instant.

### D-3 — Voix, multi-tenancy, MLflow : dans le périmètre maintenant ?
- **Voix temps réel** : coût infra + surface conformité. Maintenant, plus tard, ou hors périmètre ?
- **Multi-tenancy** : recommandation = l'inclure dès la Phase 2 (bien moins cher que rétroactif). Confirmez-vous ?
- **MLflow / MLOps complet** : nécessaire dès maintenant, ou un registre simple suffit tant qu'il n'y a pas de vrai ré-entraînement ?

### D-4 — Confirmation stack
Confirmez-vous l'adoption de la stack V2 (Next.js, FastAPI, PostgreSQL+pgvector, Redis, RabbitMQ, OTel) en **remplacement formel d'ADR-003** via un nouvel ADR-006 ? (vLLM/Triton/K8s/DVC restant conditionnels à un besoin démontré, conformément aux règles 10 et 93.)

---

## 12. Fichiers créés / modifiés

- Créé : `docs/reports/phase-0-audit-v2.md` (ce fichier).
- Modifié : aucun. Aucun code applicatif touché (règle 128, 151).

## 13. Tests exécutés

Aucun test lancé (phase d'audit, lecture seule). La suite existante (`python -m unittest discover -s tests`) est documentée comme verte à 95 tests / 93 % dans `final-report.md` et n'a pas été ré-exécutée dans le cadre de cet audit.

## 14. Critères de sortie — Gate Phase 0 (V2)

- [x] Code applicatif existant lu intégralement.
- [x] Architecture actuelle établie à partir du code, pas des déclarations.
- [x] Architecture cible V2 formalisée.
- [x] Analyse d'écart chiffrée (23 écarts, G-01 à G-23).
- [x] Contradictions du prompt identifiées et arbitrages proposés.
- [x] Stratégie de migration définie (strangler, cœur de sûreté d'abord, pas de données réelles à migrer).
- [x] Roadmap mappée sur les 23 phases du prompt, avec gates.
- [x] Critères d'acceptation transverses définis.
- [x] Registre de risques établi (13 risques, R-01 à R-13).
- [x] Aucun code produit avant l'audit.
- [ ] **Décisions utilisateur D-1 à D-4 obtenues** ← bloquant pour la Phase 1.

## 15. Conclusion

Le dépôt n'est pas une page blanche : c'est une fondation honnête et testée dont la **valeur est le cœur de sûreté et la discipline documentaire**, pas la couche technique. Le Prompt V2 impose une stack et une ambition d'une autre échelle, incompatibles avec ADR-003. La bonne approche est une **migration par strangler pattern**, cœur de sûreté porté et re-testé en premier, sans big-bang et — avantage rare — sans aucune donnée patient réelle à risquer.

L'implémentation est prête à démarrer dès que les décisions D-1 à D-4 sont prises.

STATUS : **PASS — AWAITING USER DECISIONS (D-1 to D-4)**
