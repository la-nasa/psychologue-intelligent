# PHASE REPORT

Phase : 6 (V2) — Moteur de personnalisation
Date : 2026-09-01
Objectif : `PersonalizationEngine` — résoudre un style d'interaction effectif (ton, longueur, fréquence de questions, directivité, langue, objectifs actifs) à partir des préférences déclarées, l'appliquer à la génération GREEN, **sans jamais toucher au chemin de sécurité**. Système d'objectifs (§56-57), jamais imposés.

STATUS : **PASS** — les deux classes de tests exigées passent.

---

## 1. Livré

### `PersonalizationEngine` (`app/application/personalization.py`)
`resolve_style(session, user_id) -> InteractionStyle` : combine `communication_preferences` (Phase 3) + objectifs actifs (§56) + langue du profil, avec valeurs par défaut sûres. Best-effort (jamais bloquant). Le style est exposé via `.as_context()` et tissé dans le **message système** par `ai/prompt.build_messages`, jamais ailleurs.

`build_messages` enrichi : ton (`direct`/`neutre`/`warm`), longueur (`1 à 2 phrases` / `un peu plus développées`), fréquence de questions (`peu de questions` / `une question à chaque échange`), directivité (`proposer une piste concrète` / `privilégier les questions ouvertes`), bloc « la personne travaille sur : … ».

`LocalSupportiveResponder.compose()` : produit une variation **grossière mais réelle et déterministe** selon ces marqueurs (nombre de phrases, présence d'une question, ajout d'une piste). Un vrai LLM nuancerait ; l'infrastructure de personnalisation, elle, est complète et testée.

### Système d'objectifs (`app/application/goals.py`, `app/api/goals.py`, migration `0006_goals`)
`goals` + `goal_progress` (RLS `FORCE`). `create_goal` (≤ 5 actifs, jamais auto-créé), `list_goals` (avec dernier % de progression), `record_progress` (0-100, `ACHIEVED` à 100), `list_active_titles` (alimente la personnalisation). Endpoints : `GET/POST /api/v1/goals`, `POST /api/v1/goals/{id}/progress`.

### Intégration
`ConversationOrchestrator._build_context` appelle `resolve_style` et met le style dans `ctx["interaction_style"]` (remplace les préférences brutes). Un instantané est persisté dans `conversation_state.interaction_style_json` + `language` — visible pour le clinicien plus tard.

## 2. Les deux classes de tests exigées (master prompt §85)

| Classe | Test | Vérifie |
| --- | --- | --- |
| **1 — même message, profil différent → la réponse GREEN peut varier** | `test_same_message_produces_different_replies_for_different_profiles` (unité) ; `test_same_message_different_profile_end_to_end` (HTTP, deux patients) | profil « court + peu de questions » → réponse plus courte, sans `?` ; profil « détaillé + questions + directif » → réponse plus longue, avec `?` et une piste |
| **2 — utilisateur différent, même condition de sécurité → comportement identique** | `test_safety_reply_is_identical_regardless_of_profile` | deux patients aux profils opposés envoient `"j'ai un plan suicidaire"` → **exactement le même** texte de gabarit RED, mot pour mot, même `generation_path=TEMPLATE` |

## 3. Autres invariants

- `resolve_style` retombe sur des valeurs par défaut quand rien n'est déclaré (`test_resolve_style_defaults_when_nothing_declared`).
- Un objectif n'est **jamais** créé automatiquement, même après un message où la personne exprime une intention (`test_goal_is_never_created_automatically`).
- Objectifs isolés par utilisateur ; progression sur l'objectif d'autrui → 404 ; valeur hors 0-100 → 422.

## 4. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **133 tests** (122 + 11 Phase 6), ~50 s |
| `coverage` | **91 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001→0006) |

## 5. Ce qui n'est PAS fait

- **Nuance réelle de la personnalisation** : `LocalSupportiveResponder` étant non génératif, la variation est structurelle (longueur, question, piste). Le style riche (§27 : reflet dans les mots de la personne, exploration guidée) apparaîtra avec un adaptateur `LLMProvider` génératif.
- **Inférence de style** (§21 : « ne jamais inférer des informations sensibles comme des vérités ») : le style vient uniquement de préférences **déclarées**. Un ajustement adaptatif observé (ex. « la personne répond mieux aux questions courtes ») serait une mémoire `MODEL_INFERRED` à confiance explicite — Phase 15/16.
- **Réflexion d'objectif** (§56 : « Recent reflection ») et historique de progression détaillé : `goal_progress` stocke les points ; l'écran et le fil de réflexion sont Phase 13 (Patient 360) / frontend.
- **A/B testing de style** (§120) : hors périmètre ; jamais sur une règle de sécurité.

## 6. Critères de sortie — Gate Phase 6

- [x] `PersonalizationEngine.resolve_style` : ton, longueur, fréquence de questions, directivité, langue, objectifs.
- [x] Style tissé dans le prompt système, jamais dans le chemin de sécurité.
- [x] **Classe 1** : même message + profil différent → réponse GREEN différente (unité + bout en bout).
- [x] **Classe 2** : même condition de sécurité → réponse identique quel que soit le profil.
- [x] Système d'objectifs : création (jamais automatique), progression, complétion, isolation.
- [x] Instantané de style persisté sur `conversation_state`.
- [x] `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible ; couverture 91 %.

## 7. Conclusion

La personnalisation est réelle et gouvernée : elle vient de préférences déclarées, elle fait varier la réponse GREEN de façon mesurable, et elle est **structurellement incapable** de modifier une réponse de crise — c'est la classe 2 qui l'ancre. La **Phase 7** (Safety Engine complet) remplacera l'`OutputSafety` minimal par le pipeline entier et ajoutera la suite AI red team.

STATUS : **PASS**.
