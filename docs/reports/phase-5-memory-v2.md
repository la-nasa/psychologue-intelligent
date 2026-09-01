# PHASE REPORT

Phase : 5 (V2) — Moteur de mémoire
Date : 2026-09-01
Objectif : `MemoryService` — mémoire épisodique/sémantique/longitudinale, embeddings + récupération pgvector, **oubli** (révocation de consentement en cascade, mémoire révoquée/expirée jamais réinjectée). Enrichit le contexte que le `ConversationOrchestrator` (Phase 4) assemble.

STATUS : **PASS** — `docker compose` + `pytest` verts, invariants d'oubli testés.

---

## 1. Livré

### Schéma (`0005_memory`)
- `CREATE EXTENSION vector` (image `pgvector/pgvector:pg16`).
- `memories` : `type` (`WORKING`/`EPISODIC`/`SEMANTIC`/`LONGITUDINAL`), `content_enc` (chiffré), `embedding vector(256)`, `provenance` (`USER_DECLARED`/`MODEL_INFERRED`/`CLINICIAN_VALIDATED`/`SYSTEM_DERIVED`/`TEMPORARY`), `confidence`, `sensitivity`, `consent_scope`, `status` (`ACTIVE`/`UNCERTAIN`/`EXPIRED`/`REVOKED`/`CLINICIAN_VALIDATED`), `source_conversation_id`/`source_message_id`, `expires_at`. RLS `FORCE`.
- **Index HNSW `vector_cosine_ops` partiel `WHERE status = 'ACTIVE'`** : la récupération ne peut structurellement pas remonter une mémoire non-active (TV-05).
- `longitudinal_snapshots` (tendances émotion/PHQ-9/objectifs/risque/engagement) — table + RLS ; le calcul est un job (Phase 15/16).
- `downgrade` complet, réversibilité vérifiée (0001→0005).

### Embedding (`app/ai/providers/embedding.py`)
`HashingEmbeddingModel` : sac de tri-grammes de caractères projeté et L2-normalisé, dim 256, **déterministe**. Ce n'est **pas** un encodeur sémantique (sentence-transformers = dépendance lourde + modèle à télécharger) : deux textes qui partagent du vocabulaire ont une similarité cosinus plus élevée, ce qui suffit à valider le *pipeline* de récupération. Un adaptateur `sentence-transformers` viendra en extra optionnel si le besoin est démontré.

### `MemoryService` (`app/application/memory.py`)
- `remember(...)` — chiffre, embed, insère. **`MODEL_INFERRED` exige une confiance explicite** (TV-04) ; `CLINICIAN_VALIDATED` n'est pas une provenance libre-service.
- `retrieve(user_id, query_text, limit, types)` — embed de la requête → recherche vectorielle (`cosine_distance`) parmi **`status = 'ACTIVE'` et non expirées** → re-classement `0.7·pertinence + 0.15·récence + 0.15·confiance` → top-K, contenu déchiffré.
- `forget_for_consent(purpose)` — révocation de consentement → `status = 'REVOKED'` (tout si `CARE`, sinon les mémoires du `consent_scope`).
- `expire_due(now)` — passe `ACTIVE`→`EXPIRED` pour les mémoires échues (worker/cron plus tard ; le retrieval filtre déjà par fenêtre d'expiration).

### Intégration au moteur de conversation
- `consent.revoke` appelle `memory.forget_for_consent` (import différé, pas de cycle).
- `ConversationOrchestrator._build_context` : après le profil et l'historique, `memory.retrieve(query=message courant, limit=3, types=EPISODIC/SEMANTIC)` → `ctx["relevant_memories"]`.
- `ai/prompt.py::build_messages` : bloc « éléments partagés lors d'échanges précédents » — **encadré comme contexte, jamais comme instruction ni fait établi** (TV-03/TV-04), à n'évoquer que si pertinent.
- Après un tour **GREEN**, une mémoire `EPISODIC` / `USER_DECLARED` est créée à partir du message patient (ses mots, confiance 1.0, `source_message_id`). **Les tours ORANGE/RED n'archivent rien** — on ne réinjecte pas un message de crise (décision de périmètre ; la revue clinique de ce point = Phase 14). Best-effort : un échec de mémoire ne casse jamais la conversation.

## 2. Invariants vérifiés

| Invariant (overview-v2 §15 / threat-model-v2) | Test |
| --- | --- |
| **TV-05** — mémoire révoquée jamais réinjectée | `test_memory.py::test_revoked_memory_is_never_retrieved` ; bout en bout : `test_memory_integration.py::test_revoking_care_consent_forgets_conversation_memory` |
| **TV-05** — mémoire expirée jamais réinjectée | `test_memory.py::test_expired_memory_is_never_retrieved` (exclue au retrieval + `expire_due`) |
| **TV-04** — `MODEL_INFERRED` exige une confiance explicite | `test_memory.py::test_model_inferred_memory_requires_explicit_confidence` |
| **TV-04** — un patient ne crée pas de mémoire `CLINICIAN_VALIDATED` | `test_memory.py::test_patient_cannot_create_a_clinician_validated_memory` |
| Isolation inter-utilisateur et inter-organisation | `test_memory.py::test_memories_are_isolated_between_users`, `::..._organizations` |
| La récupération remonte la mémoire pertinente, pas le bruit | `test_memory.py::test_retrieval_ranks_the_topically_relevant_memory_first` |
| Un tour GREEN écrit une mémoire épisodique ; un tour de crise n'écrit rien | `test_memory_integration.py::test_green_turn_writes_an_episodic_memory`, `::test_crisis_turn_does_not_write_a_memory` |
| Un message antérieur est récupérable comme contexte au tour suivant | `test_memory_integration.py::test_earlier_message_is_retrievable_as_context_on_a_later_turn` |

## 3. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **122 tests** (110 + 12 Phase 5), ~26 s |
| `coverage` | **92 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres (`pgvector` sans stubs → `ignore_missing_imports` ciblé) |
| `alembic downgrade base && upgrade head` | réversible (0001→0005) |

## 4. Ce qui n'est PAS fait

- **Embedding sémantique réel** : `HashingEmbeddingModel` est lexical, pas sémantique. Un adaptateur `sentence-transformers` (ou service d'embedding) le remplacera si la qualité de récupération lexicale s'avère insuffisante en usage réel.
- **Working memory dans Redis** : le contexte de tour porte déjà les 6 derniers messages ; un cache Redis dédié (résumé de session, presence) viendra avec le besoin.
- **Semantic / Longitudinal dérivés** : les tables existent ; le calcul (extraction de faits récurrents, agrégation de tendances) est un job — Phase 15 (analytics) / 16 (apprentissage).
- **Extraction de faits par LLM** : la mémoire épisodique = le message brut du patient (défendable, aucune inférence). L'extraction structurée « la personne a un problème de sommeil » nécessite un LLM et une revue — plus tard.
- **`CLINICIAN_VALIDATED` récupérable** : le statut existe ; l'endpoint de validation clinicien et son inclusion au retrieval = Phase 14.
- **Purge physique** d'une mémoire révoquée : `REVOKED` la sort du retrieval ; l'effacement définitif suit la politique de rétention (comme les demandes de suppression, Phase 3).

## 5. Critères de sortie — Gate Phase 5

- [x] `memories` + pgvector + index HNSW partiel sur `status='ACTIVE'`.
- [x] `MemoryService` : `remember` / `retrieve` / `forget_for_consent` / `expire_due`.
- [x] Récupération : embed → recherche vectorielle → filtrage statut/expiration → re-classement pertinence/récence/confiance.
- [x] **Oubli** : révocation de consentement → cascade `REVOKED` ; mémoire révoquée/expirée jamais renvoyée (testé unitairement **et** bout en bout).
- [x] Provenance : `MODEL_INFERRED` avec confiance explicite ; pas d'auto-`CLINICIAN_VALIDATED`.
- [x] Intégration orchestrateur : mémoire épisodique écrite (GREEN seulement), récupérée au tour suivant, encadrée comme donnée dans le prompt.
- [x] Isolation inter-utilisateur / inter-organisation.
- [x] `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible ; couverture ≥ 85 %.

## 6. Conclusion

Le contexte que l'orchestrateur assemble n'est plus limité à la fenêtre courante : la mémoire épisodique persiste et remonte quand elle est pertinente, et elle **disparaît réellement** quand le consentement est retiré — l'invariant TV-05 est le cœur de cette phase et il est vérifié des deux côtés. La **Phase 6** (personnalisation) exploitera les préférences de communication (Phase 3) et cette mémoire pour faire varier ton, longueur et directivité — avec les tests « même message + profil différent » / « utilisateur différent + même condition de sécurité ».

STATUS : **PASS**.
