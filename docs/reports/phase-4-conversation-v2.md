# PHASE REPORT

Phase : 4 (V2) — Moteur de conversation
Date : 2026-09-01
Objectif : Conversation et messages persistés, streaming (SSE) avec interruption, `ConversationOrchestrator`, `DialoguePolicy` (FAST/DEEP), `ModelRouter` (local / externe conditionné au consentement `AI_EXTERNAL` — ADR-007), `OutputSafety` minimal. **Premier consommateur HTTP réel du pipeline de sûreté porté en Phase B.**

STATUS : **PASS** — `docker compose` + `pytest` verts, invariants testés.

---

## 1. Livré

### Schéma (`0004_conversation`)
3 tables RLS `FORCE` : `conversations`, `messages` (contenu **chiffré au repos**, `generation_path` ∈ `FAST/DEEP/TEMPLATE`, `llm_provider`, `crisis_event_id`), `conversation_state` (stage, `risk_state`, `interaction_style`, langue). `downgrade` complet.

### AI — ports et adaptateurs (`app/ai/`)
- `prompt.py` — `SYSTEM_PROMPT` + `build_messages` portés de v1. **`about_me` encadré comme information, jamais instruction** (TV-03) ; préférences de style et One-Question Policy tissées dans le message système.
- `providers/base.py` — `StreamingLLMProvider` (async), `LLMProvider` (sync, conservé pour `compose_reply`), `ProviderUnavailable`.
- `providers/local.py` — `LocalSupportiveResponder` : répondeur de soutien **non génératif**, streamé (ACKNOWLEDGE → reflet → une question). Défaut du FAST path et repli du DEEP. Pas une IA conversationnelle — en attendant un adaptateur `local` réellement génératif (llama.cpp) ou `external`.
- `providers/external.py` — `ExternalLLMProvider` : streaming OpenAI-compatible. **Inerte sans `PI_LLM_EXTERNAL_API_KEY`** (`health_check → False`, `stream → ProviderUnavailable`). Le chemin réseau est `# pragma: no cover` (nécessite clé + réseau) ; la logique de routage/repli est testée avec un faux fournisseur.
- `routing/dialogue_policy.py` — `classify` → `FAST` (court, historique léger, charge émotionnelle faible) ou `DEEP` + `one_question_only` si charge élevée.
- `routing/model_router.py` — `route()` : FAST→local ; DEEP+consentement+externe sain→external ; DEEP sinon→**local (dégradation, jamais de transfert non consenti)**.

### Application
- `application/conversation.py` — `ConversationOrchestrator` :
  - `get_or_create_active_conversation` — **exige `CARE`**, idempotent tant qu'active.
  - `stream_turn` — persiste le message patient (chiffré) → **`evaluate_incoming_message` (Phase B) AVANT toute génération** → si ORANGE/RED : `compose_reply(decision, templates, _RaisingLLM(), …)` (l'espion lève s'il est appelé) → si GREEN : contexte minimal, `classify`, `route`, streaming, `OutputSafety`, persistance. Interruption : `cancel: asyncio.Event` → le flux s'arrête, la réponse partielle est persistée et marquée `+interrupted`. Met à jour `conversation_state` (`risk_state`, `stage`).
  - `send_message` — variante non streamée (consomme `stream_turn`).
  - `get_messages` — historique déchiffré, chronologique.
- `application/output_safety.py` — version minimale (Phase 7 = pipeline complet) : refuse une sortie vide, une revendication de diagnostic/posture clinique, une incohérence de crise (appel sur non-GREEN) → `SAFE_FALLBACK`, jamais la sortie brute.

### API
`POST /api/v1/conversations` · `POST /api/v1/conversations/{id}/messages` (non streamé) · `POST /api/v1/conversations/{id}/messages/stream` (SSE, détecte la déconnexion client → interruption) · `GET /api/v1/conversations/{id}/messages`. Rate limit distribué 30 messages/min/patient.

## 2. Invariants vérifiés

| Invariant (overview-v2 §15) | Test |
| --- | --- |
| 1 — LLM ne décide jamais d'une crise ; ORANGE/RED → gabarit fixe, aucun fournisseur appelé | `test_conversation.py::test_red_message_gets_the_fixed_template_and_opens_an_alert` ; `_RaisingLLM` dans `compose_reply` ; `test_conversation_stream.py::test_red_stream_sends_the_template_as_a_single_chunk` |
| 3 — ressource clinique filtrée par organisation + patient | `test_conversation.py::test_cannot_post_to_another_patients_conversation`, `::test_conversations_are_isolated_between_organizations` |
| 7 — aucune donnée ORANGE/RED vers un fournisseur externe | par construction (non-GREEN ne passe jamais par le routeur) + `test_conversation_routing` |
| 8 — DEEP exige un consentement `AI_EXTERNAL` actif ; sinon dégradation locale | `test_conversation_routing.py::test_deep_without_consent_degrades_to_local` |
| — `CARE` requis pour converser | `test_conversation.py::test_starting_a_conversation_requires_care_consent` |
| — `about_me` traité comme donnée, pas instruction (TV-03) | `test_conversation_routing.py::test_about_me_is_framed_as_information_never_as_instruction` |
| — contenu de message chiffré au repos | `test_conversation.py::test_message_content_is_encrypted_at_rest` |
| — interruption : flux arrêté, réponse partielle persistée et marquée | `test_conversation_interrupt.py` |
| — ce qui est streamé == ce qui est persisté (GREEN non interrompu) | `test_conversation_stream.py::test_green_stream_yields_...` |

## 3. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **110 tests** (79 + 31 Phase 4) |
| `coverage` | **91 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001→0004) |

Vitesse de la suite : **~23 s** (110 tests). Optimisée après la Phase 4 :
boucle d'événements unique pour la session (`asyncio_default_*_loop_scope = "session"`) + vrai pool de
connexions au lieu de `NullPool` ; nettoyage inter-test par `DELETE FROM` en ordre de FK au lieu de
`TRUNCATE ... CASCADE` (le `TRUNCATE` sur Docker Desktop coûtait ~2 s par test) ; limites de débit basses
en environnement `testing`. Gain ~9x (3 min 30 → 23 s).

## 4. Ce qui n'est PAS fait

- **Répondeur génératif réel** : `LocalSupportiveResponder` est non génératif (honnête, comme le templated de v1). Adaptateur llama.cpp `local` génératif + activation réelle de `external` : quand une clé / un hébergement GPU sont fournis. La latence CPU (ADR-005) reste le blocage connu.
- **Working memory / retrieval sémantique** : le contexte se limite aux 6 derniers messages + profil + préférences. `MemoryService` (4 niveaux, pgvector) = **Phase 5**.
- **Redis pour l'état de dialogue** : `conversation_state` n'est qu'en PostgreSQL pour l'instant (snapshot). Le cache Redis (working memory, presence) vient avec la Phase 5.
- **`OutputSafety` complet** (PII, hallucination, cohérence fine) : Phase 7.
- **Bande de sévérité PHQ-9 dans le contexte** : Phase 8 (l'accroche `phq9_severity_band` existe déjà dans `build_messages`).
- **WebSocket** : seul SSE est implémenté pour le stream texte ; WS (transcript, presence, notifications) et WebRTC = Phase 11 (voix).
- **v1 intacte**. Retrait de `backend/app/{conversation,responder,ai,local_llm}.py` : après les 4 parcours E2E du prompt maître sur V2 (Phase 17/22).

## 5. Critères de sortie — Gate Phase 4

- [x] Conversation + messages persistés, chiffrés, patient-scopés.
- [x] Streaming SSE avec séquence d'événements cohérente.
- [x] Interruption texte : flux arrêté, réponse partielle persistée et marquée.
- [x] `ConversationOrchestrator` appelle le pipeline de sûreté **avant** toute génération.
- [x] `DialoguePolicy` FAST/DEEP + One-Question Policy.
- [x] `ModelRouter` : chemin externe conditionné au consentement `AI_EXTERNAL`, dégradation locale sinon.
- [x] `OutputSafety` minimal : jamais la sortie brute en cas d'échec.
- [x] `pytest` vert (110), couverture 91 %.
- [x] `ruff` / `mypy` / `bandit` / `pip-audit` propres ; migration réversible.

## 6. Conclusion

Le moteur de conversation relie enfin toutes les briques : consentement (Phase 3) → sûreté (Phase B) → routage → génération → vérification de sortie → persistance, avec streaming et interruption. La **Phase 5** (moteur de mémoire : working/episodic/semantic/longitudinal, retrieval pgvector, oubli, révocation) enrichira le contexte que cet orchestrateur assemble.

STATUS : **PASS**.
