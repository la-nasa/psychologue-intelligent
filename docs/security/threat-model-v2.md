# Threat model V2

Établi : Phase 1 (2026-08-28). Étend `docs/security/threat-model.md` (v1, 16 menaces TH-01…TH-16).
Ce document couvre les **nouvelles frontières de confiance** introduites par la stack V2 (ADR-006), la stratégie LLM hybride (ADR-007) et le multi-tenancy (ADR-008). Les menaces v1 restent valables ; celles dont la mitigation change sur la nouvelle stack sont annotées.

Cadres de référence : STRIDE, OWASP Top 10, OWASP API Security Top 10, **OWASP Top 10 for LLM Applications (2025)**, **NIST AI RMF + profil Generative AI (NIST-AI-600-1)**.

> Règle de projet héritée de v1 : ce document est révisé à **chaque phase** qui touche une frontière de confiance, et chaque menace porte un **statut de vérification tracé à un test réel**, jamais une déclaration d'intention. En Phase 1, tous les statuts sont `PLANIFIÉ` — ils deviennent `VÉRIFIÉ` quand le test existe et passe.

---

## 1. Actifs (inchangés + ajouts)

Identité et données cliniques, consentements, sessions, politiques de crise, décisions et alertes, contenu de conversation, **mémoire et embeddings**, modèles/datasets, secrets (**dont clé API LLM externe**), audit, canaux de notification, **flux audio voix**, **frontière d'isolation d'organisation**.

## 2. Frontières de confiance V2

```text
Client (patient/clinicien/admin, Next.js)  ↔  API FastAPI            [TB-1]
API  ↔  PostgreSQL (RLS)                                             [TB-2]
API  ↔  Redis (état éphémère, rate limit, locks)                     [TB-3]
API  ↔  RabbitMQ  ↔  Workers                                         [TB-4]
API / Workers  ↔  Modèle LLM local (in-process ou vLLM réseau)       [TB-5]
API  ↔  Modèle LLM EXTERNE (Anthropic / OpenAI-compatible)  ← NOUVEAU, réseau sortant [TB-6]
Voice Session Manager  ↔  navigateur (WebRTC média)  ← NOUVEAU       [TB-7]
Voice  ↔  STT / TTS (local ou service)  ← NOUVEAU                    [TB-8]
Organisation A  ⇹  Organisation B (isolation logique, même base)  ← NOUVEAU [TB-9]
API  ↔  Stockage objet (audio, artefacts modèles)  ← NOUVEAU        [TB-10]
Production  ↔  pipeline d'apprentissage  ↔  MLflow                   [TB-11]
Observabilité (traces/logs/métriques) — exfiltration potentielle    [TB-12]
```

---

## 3. Registre — nouvelles menaces V2

| ID | Menace | Frontière | Catégorie | Risque | Mitigation de conception | Vérification |
| --- | --- | --- | --- | --- | --- | --- |
| **TV-01** | **Fuite inter-tenant** : un utilisateur de l'org A lit/écrit une ressource de l'org B (BOLA cross-tenant) | TB-9 | Elevation / API1 / API5 | **Critique** | ADR-008 : `organization_id NOT NULL` sur chaque table de tenant + **RLS PostgreSQL** filtrant sur `app.current_organization` (deny-by-default au niveau moteur) + `TenantScopedRepository` applicatif + trigger same-org sur les relations. `SUPER_ADMIN` seul cross-org, audit renforcé. | PLANIFIÉ — suite `tests/security/test_tenant_isolation.py` exécutée **à chaque phase** : lecture/écriture croisée refusée sur patient, conversation, alerte, PHQ-9, feedback, dataset ; admin A ne voit pas users B ; relation cross-org refusée ; jeton sans `organization_id` rejeté |
| **TV-02** | **Exfiltration de données patient vers le LLM externe** au-delà du strict nécessaire, ou sans consentement | TB-6 | Information disclosure / LLM02 (sensitive info disclosure) | **Critique** | ADR-007 : chemin DEEP **conditionné à un consentement `AI_EXTERNAL` actif** ; sans lui → dégradation locale, jamais transfert. `ContextBuilder` minimise (jamais score PHQ-9 brut, jamais données d'un autre patient, jamais identifiant direct). **Aucune donnée ORANGE/RED n'atteint jamais le générateur** donc jamais l'externe. Contenu envoyé journalisé (métadonnées, pas le texte) avec `correlation_id`. | PLANIFIÉ — `test_deep_path_requires_ai_external_consent`, `test_revoked_ai_external_consent_downgrades_to_local`, `test_orange_red_never_calls_any_llm` (moteur espion), `test_external_context_excludes_raw_phq9_and_other_patients` |
| **TV-03** | **Prompt injection** via message, `about_me`, **ou contenu de mémoire/RAG réinjecté** — pour extraire le prompt système, d'autres données, ou détourner la réponse | TB-1, TB-5, TB-6 | LLM01 (prompt injection) | **Élevé, borné par construction** | Contenu récupéré (mémoire, RAG, `about_me`) encadré dans le prompt comme **données, jamais instructions** (`_build_messages`). Prompt système non divulgable. Le LLM n'a **aucun accès** à la politique de sécurité, ne peut pas la « désactiver ». Rayon d'impact borné : la crise est décidée **avant et hors** de tout LLM → au pire une réponse GREEN inappropriée, jamais un contournement de classification. `OutputSafety` en aval. | PLANIFIÉ — **suite AI red team versionnée** (`tests/ai_redteam/`) : corpus injection/jailbreak/extraction de prompt système/empoisonnement de contexte, multilingue (fr/en + mix). Phase 7 (première passe), Phase 18 (complète) |
| **TV-04** | **Empoisonnement de mémoire** : un patient (ou un compte compromis) insère dans la mémoire sémantique des contenus qui orientent durablement les réponses futures, ou de fausses « informations validées » | TB-2 | LLM04 (data & model poisoning) / Tampering | **Élevé** | Mémoire typée par **provenance** (`USER_DECLARED`/`MODEL_INFERRED`/`CLINICIAN_VALIDATED`/`SYSTEM_DERIVED`/`TEMPORARY`) et **confiance explicite** ; `MODEL_INFERRED` jamais traité comme fait ; seul un clinicien peut poser `CLINICIAN_VALIDATED` ; retrieval pondère par confiance et récence ; une mémoire ne peut pas s'auto-promouvoir. Isolation tenant (TV-01) empêche l'empoisonnement cross-org. | PLANIFIÉ — `test_model_inferred_memory_never_overrides_user_declared`, `test_patient_cannot_create_clinician_validated_memory`, `test_low_confidence_memory_is_deprioritized_in_retrieval` |
| **TV-05** | **Mémoire supprimée / consentement révoqué toujours réinjecté** dans le contexte | TB-2, TB-5, TB-6 | Privacy / GDPR | **Critique** | Statut de mémoire (`ACTIVE`/`REVOKED`/`EXPIRED`) ; index vectoriel **partiel `WHERE status='ACTIVE'`** ; `revoke_consent('CARE')` → `UPDATE memories SET status='REVOKED'` en cascade ; le retrieval ne lit jamais une mémoire non-`ACTIVE`. | PLANIFIÉ — `test_revoked_memory_never_appears_in_any_context`, `test_expired_memory_excluded`, `test_deleted_memory_excluded`, `test_consent_revocation_cascades_to_memory` (exécuté à chaque phase touchant la mémoire) |
| **TV-06** | **Sortie non sûre du LLM** : réponse générée qui pose un diagnostic, minimise un risque (fausse réassurance), invente un fait, ou divulgue un contenu système | TB-5, TB-6 | LLM09 (misinformation) / LLM06 (excessive agency) / Safety | **Critique** | `OutputSafety` obligatoire sur **toute** réponse générée (locale ET externe) : `PII check → safety check → clinical policy check → crisis consistency check → hallucination / unsupported claim check`. Échec → `SAFE_FALLBACK` (message neutre + ressources), jamais la sortie brute. Prompt système interdit explicitement diagnostic et réassurance non étayée. | PLANIFIÉ — `tests/safety/test_output_safety.py` (chaque filtre), `test_generated_diagnosis_claim_is_blocked`, `test_response_inconsistent_with_crisis_decision_is_replaced`, `test_output_safety_failure_yields_safe_fallback` |
| **TV-07** | **Excessive agency** : si des outils sont ajoutés (recherche, calendrier…), le LLM décide seul d'un appel à privilège | TB-5 | LLM06 | **Élevé (préventif)** | Aujourd'hui : **aucun outil**. Si ajoutés (§62) : `Tool Registry` + `Permission Policy` + validation de paramètres + timeout + rate limit + audit ; un modèle ne choisit jamais librement l'outil. Le crisis engine reste hors de portée de tout outil. | PLANIFIÉ — pas d'outil en Phase 1–10 ; menace ré-évaluée si/quand des outils sont introduits |
| **TV-08** | **Interception / rétention abusive du flux audio voix** ; audio brut conservé indéfiniment ; audio traité comme donnée biométrique sans base légale | TB-7, TB-8, TB-10 | Information disclosure / Privacy | **Critique** | _(Phase 11)_ Consentement `VOICE` explicite et distinct ; indication claire d'enregistrement ; **rétention configurable, courte par défaut** ; suppression sur demande ; chiffrement en transit (DTLS/SRTP via WebRTC) et au repos ; traitement STT/TTS local privilégié ; l'audio brut n'est **pas** conservé par défaut après transcription. PIA voix avant activation. | PLANIFIÉ (Phase 11) — `tests/voice/test_audio_retention.py`, `test_raw_audio_deleted_after_transcription`, `test_voice_requires_explicit_consent` |
| **TV-09** | **Compromission de la clé API LLM externe** (dans Git, logs, variable d'env exposée) → usage frauduleux, coût, exfiltration via un tiers | TB-6 | API8 / secrets | **Élevé** | Clé dans gestionnaire de secrets, **jamais dans Git** (`scan_secrets.py` étendu + gitleaks en CI), jamais dans les logs (redaction), rotation documentée (runbook), quota/alerte de coût côté fournisseur, egress réseau restreint à l'endpoint du fournisseur. | PLANIFIÉ — gitleaks + `scan_secrets.py` en CI (bloquant) ; `test_llm_provider_key_never_in_response_or_logs` |
| **TV-10** | **Poison via RabbitMQ** : un message de job forgé/rejoué déclenche un traitement non voulu (ré-embedding, ré-échantillonnage, notification) | TB-4 | Tampering / API | **Moyen** | Broker en réseau privé, identifiants dédiés par consommateur, messages signés/typés (Pydantic), **idempotence** de chaque handler (clé de job), pas de donnée sensible en clair dans le message (référence + lecture DB scopée), DLQ pour les messages non traitables. | PLANIFIÉ — `test_job_handlers_are_idempotent`, `test_malformed_job_goes_to_dlq_not_crash` |
| **TV-11** | **Redis comme source de vérité accidentelle** : une donnée clinique (état de dialogue, décision) n'existe qu'en cache et est perdue au flush | TB-3 | Availability / integrity | **Moyen** | Règle d'architecture (overview-v2 §9) : Redis ne stocke jamais une donnée clinique critique comme **seule** copie ; `conversation_state` a un snapshot PostgreSQL ; les décisions de risque/crise sont persistées en base avant toute réponse. Redis chiffré en transit, réseau privé, pas d'exposition publique. | PLANIFIÉ — `test_dialogue_state_survives_redis_flush`, revue d'architecture par module |
| **TV-12** | **Ré-identification via analytics ou observabilité** : `analytics_events` ou traces OTel contiennent du contenu clinique ou un identifiant direct | TB-12 | Privacy / LLM02 | **Élevé** | `analytics` ne lit **jamais** une table clinique — uniquement des événements de domaine, sur `subject_pseudonym` **tournant** ; aucune trace/log ne contient contenu de message, jeton, secret (règle v1 TH-09 étendue) ; processeur OTel avec redaction ; rétention observabilité minimisée. | PLANIFIÉ — `test_analytics_events_contain_no_pii_no_content`, `test_otel_spans_are_redacted`, scan périodique des logs réels (dette v1 TH-09 à combler) |
| **TV-13** | **Déni de service sur le chemin LLM** : messages volumineux/rapides saturent le modèle (local sérialisé, ou coût externe) | TB-5, TB-6 | LLM10 (unbounded consumption) / DoS | **Élevé** | Rate limit **distribué** (Redis) par patient sur l'envoi de message ; taille de message bornée ; file d'inférence locale avec profondeur max + rejet propre (`SAFE_FALLBACK` « je prends un instant ») ; budget de tokens par tour ; quota de coût externe par organisation. | PLANIFIÉ — `test_message_flood_is_rate_limited_across_instances`, `test_inference_queue_depth_limit_degrades_gracefully` |
| **TV-14** | **Supply chain** : dépendance compromise (PyPI/npm), image de base, poids de modèle téléchargé | TB-2..TB-11 | LLM03 (supply chain) / A06 | **Élevé** | `pip-audit` + `npm audit` + `trivy` (conteneurs) en CI, bloquants sur critique ; lockfiles committés ; poids de modèle vérifiés par **checksum** avant acceptation (déjà fait en v1 `bootstrap_llm_model.py`, à généraliser) ; images de base minimales et épinglées ; SBOM générée (`cyclonedx`). | PLANIFIÉ — gates CI ; `test_model_weight_checksum_is_enforced` |
| **TV-15** | **Altération du registre de modèles / promotion non approuvée** en environnement (SHADOW→PRODUCTION) | TB-11 | Tampering / Safety | **Critique** | Repris de v1 TH-08/SEC-001 : `UNIQUE(model_version_id, approver_id)` + **2 approbations distinctes** + transition atomique `UPDATE ... WHERE status=<lu>` ; un `REJECTED` bloque définitivement ; promotion d'environnement auditée ; rollback testé. MLflow n'est **pas** l'autorité — la base l'est. | PLANIFIÉ — portage de `test_learning_pipeline.py` (double approbation, rejet bloquant, race condition) + `test_environment_promotion_requires_approval` |

---

## 4. NIST AI RMF — couverture (profil GenAI)

| Fonction | Application au projet | Où |
| --- | --- | --- |
| **GOVERN** | Gouvernance clinique (comité psychiatre/psy/éthique/biostat — §99), politique d'oversight humain, ADR tracés, ce threat model révisé à chaque phase | `docs/clinical/` _(Phase 21)_, ADR |
| **MAP** | Contexte d'usage identifié (santé mentale, public vulnérable), risques GenAI catalogués (ce document TV-01…TV-15), acteurs et impacts | Phase 0 audit, ce document |
| **MEASURE** | Éval offline/safety/clinique de chaque modèle (§46) ; métriques crisis recall/precision, faux négatifs/positifs, sorties non sûres ; AI red team ; robustesse (typo, slang, variantes fr, langue mixte, adversarial) | Phases 7, 16, 17, 18, 22 |
| **MANAGE** | `SAFE_FALLBACK`, rollback de modèle testé, escalade d'incident, feature flags pour désactiver un composant, suivi de coût | overview-v2 §7, `docs/deployment/rollback.md`, runbook |

## 5. Menaces v1 dont la mitigation évolue en V2

| v1 | Évolution V2 |
| --- | --- |
| TH-01 (session/credential stuffing) | PBKDF2 → **Argon2id** (dépendance désormais permise, ADR-006) ; rate limit **distribué** (Redis) au lieu de mémoire de processus |
| TH-04 (prompt injection) | Reclassée et élargie en **TV-03 + TV-06** (chemin externe inclus, mémoire/RAG inclus) |
| TH-06 / TM-08 (perte/doublon notification) | **Outbox transactionnelle stricte** (ligne écrite dans la transaction de l'alerte, envoi par worker) ferme le cas résiduel v1 |
| TH-10 (DoS, rate limit mémoire) | Rate limit **distribué Redis**, partagé entre instances ; + **TV-13** (chemin LLM) |
| TH-13 (connexion SQLite partagée) | Sans objet — SQLAlchemy async + pool de connexions PostgreSQL |
| TH-09 (logs sensibles) | Étendu à OTel (traces/métriques) → **TV-12** ; scan de logs réels toujours en dette, à combler Phase 18 |

## 6. Dette de vérification (Phase 1 → à combler)

- Tous les statuts ci-dessus sont `PLANIFIÉ`. Chaque phase qui implémente un composant **doit** livrer les tests correspondants et passer le statut à `VÉRIFIÉ` dans ce document.
- Pentest externe et AI red team par un tiers : Phase 22, non substituables par les tests internes.
- PIA (analyse d'impact vie privée) globale + PIA voix spécifique : Phase 21–22.
- Qualification réglementaire (AI Act : le produit est probablement « à haut risque ») : conseil juridique spécialisé, hors périmètre de l'agent.
