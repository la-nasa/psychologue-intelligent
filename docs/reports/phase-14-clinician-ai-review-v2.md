# PHASE REPORT

Phase : 14 (V2) — Clinician AI Review
Date : 2026-09-01
Objectif : Permettre à un clinicien de **noter une réponse de l'assistant** à
l'un de ses patients suivis — décision `APPROVE` / `EDIT` / `REJECT` /
`FLAG_SAFETY`, 7 dimensions sur 1-5, une catégorie de retour, une correction
proposée, un commentaire — le tout **à usage non punitif** (jamais pour évaluer
un clinicien).

STATUS : **PASS** — gate complète verte (292 tests, couverture 90 %).

---

## 1. Analyse

Roadmap audit Phase 14 : « Clinician AI Review : APPROVE/EDIT/REJECT/FLAG,
évaluation structurée 1-5, feedback structuré (catégories), perf dashboard
clinicien | Tests feedback + **non-usage punitif documenté** ». `data-model-v2`
§104 spécifie déjà la table `clinician_response_reviews` (decision, scores_json
7 dimensions, feedback_type, corrected_response_enc, clinical_comment_enc,
model_version, policy_version). Le design-system §147 (`AiReviewCard`) confirme
les 7 dimensions et les 4 actions.

Rien à porter de la v1 : `backend/app/learning.py::human_feedback` concerne
l'échantillonnage de **messages patients** pour l'entraînement (Phase 16), pas la
revue des **réponses de l'IA**.

## 2. Conception

| Décision | Choix |
| --- | --- |
| Cible | Un message `author_type='ASSISTANT'`. Erreur `not_reviewable` si on vise un message patient. |
| Porte d'accès | Relation `ACTIVE` patient-clinicien (`relationships.require_active_relationship`) — cohérent avec Phases 12–13. Le contenu de l'échange (message patient + réponse IA) est montré au clinicien référent **pour cette revue** ; c'est un acte de supervision clinique légitime, pas la synthèse minimale de la Phase 13. |
| Décisions | `APPROVE` / `EDIT` / `REJECT` / `FLAG_SAFETY`. `EDIT` **exige** `corrected_response` (CHECK en base `ck_review_edit_has_correction` + garde applicative). |
| Notes | Les 7 dimensions `empathy, relevance, personalization, context, safety, clarity, usefulness`, chacune entier 1..5, **toutes requises** (`_validate_scores` : ensemble exact + bornes + rejet des booléens). |
| Catégorie | Vocabulaire fixe : `TONE, CLINICAL_ACCURACY, PERSONALIZATION, CONTEXT_UNDERSTANDING, SAFETY, RELEVANCE, OTHER`. |
| Unicité | Une revue par `(message_id, reviewer_id)` (`uq_review_message_reviewer`). Plusieurs cliniciens référents peuvent chacun ajouter la leur. Collision → **409**. |
| `FLAG_SAFETY` | Persisté + audit dédié `ai_review.safety_flag` (WARNING) + exposé par `list_safety_flags` pour l'équipe sécurité. **Ne modifie jamais** automatiquement une politique de crise (invariant Phase 7/9 : moteur de crise indépendant). |
| model_version | Repris de `message.responder_version`. `policy_version` nullable (une réponse GREEN n'en a pas). |
| Chiffrement | `corrected_response_enc`, `clinical_comment_enc` chiffrés au repos (Fernet). |

### Usage non punitif — invariant de gouvernance

Note dédiée : [`docs/governance/ai-review-non-punitive.md`](../governance/ai-review-non-punitive.md).

| Garantie | Mise en œuvre |
| --- | --- |
| Aucune agrégation par relecteur | `model_quality_report` agrège **par `model_version` / `decision` / `feedback_category` / dimension** ; sa signature n'accepte pas de paramètre relecteur ; sa sortie ne contient aucun identifiant de personne. |
| Nom d'API | Aucune fonction publique du module ne contient `per_reviewer`, `by_reviewer`, `reviewer_stat`, `clinician_perf`, `reviewer_scorecard` — vérifié par introspection. |
| Audit | `ai_review.submit` journalise `decision` + `feedback_category` + `model_version` — jamais un agrégat par personne. |

## 3. Implémentation — fichiers

| Fichier | Rôle |
| --- | --- |
| `app/alembic/versions/0011_ai_review.py` | Table `clinician_response_reviews` (RLS forcée + politique, `uq_review_message_reviewer`, 2 CHECK, index `ix_reviews_org_decision` / `ix_reviews_model`). Réversible. |
| `app/infrastructure/models.py` | Modèle `ClinicianResponseReview` (docstring : usage non punitif). |
| `app/application/ai_review.py` (nouveau) | `submit_review`, `list_reviewable`, `reviews_for_message`, `model_quality_report`, `list_safety_flags` ; `DECISIONS`, `SCORE_DIMENSIONS`, `FEEDBACK_CATEGORIES`. |
| `app/api/ai_review.py` (nouveau) | Router `/api/v1/clinician/ai-review` : `GET /patients/{id}/messages`, `POST /messages/{id}/review`, `GET /messages/{id}/reviews` (rôles `PSYCHOLOGIST`/`CLINICAL_SUPERVISOR`) ; `GET /quality-report`, `GET /safety-flags` (rôles `CLINICAL_SUPERVISOR`/`SUPER_ADMIN`). |
| `app/api/schemas.py` | `AiReviewRequest`. |
| `app/main.py` | Router `ai_review` inclus. |
| `docs/governance/ai-review-non-punitive.md` (nouveau) | Note de gouvernance. |
| `tests/conftest.py` | `clinician_response_reviews` en tête de `_CLEAN_ORDER` (avant `messages`). |
| `tests/test_ai_review.py` (nouveau) | 12 tests. |

## 4. Invariants vérifiés

| Invariant | Test |
| --- | --- |
| Notes : les 7 dimensions requises, 1..5, booléens rejetés | `test_ai_review::test_scores_must_cover_every_dimension_within_range` |
| `EDIT` sans correction → refus ; avec correction → persistée (chiffrée) | `::test_edit_requires_a_corrected_response` |
| Seul un message assistant est reviewable | `::test_only_an_assistant_message_can_be_reviewed` |
| Pas de relation `ACTIVE` → 403 | `::test_review_requires_an_active_relationship` |
| Une revue par (message, relecteur) ; un autre référent peut ajouter la sienne | `::test_one_review_per_message_per_reviewer` |
| `FLAG_SAFETY` → audit `ai_review.safety_flag` + listé pour l'équipe sécurité | `::test_safety_flag_is_recorded_and_listed` |
| **Rapport qualité agrégé par modèle, jamais par relecteur ; zéro identifiant de personne en sortie** | `::test_quality_report_aggregates_by_model_not_reviewer` |
| **Le module n'expose aucune statistique par clinicien** (introspection) | `::test_module_exposes_no_per_reviewer_aggregation` |
| La règle d'usage non punitif est documentée dans le module | `::test_module_documents_the_non_punitive_rule` |
| `PATIENT` refusé sur toute la surface (403) | `::test_patient_cannot_touch_ai_review` |
| Bout-en-bout HTTP : lister → reviewer (`EDIT`) → relire → rapport qualité | `::test_clinician_http_review_flow` |
| `model_version` capturé depuis la réponse ; `APPROVE` sans correction | `::test_approve_review_persists_scores_and_model_version` |

## 5. Résultats de vérification (image `server`, PG + Redis + Mailpit)

| Contrôle | Résultat |
| --- | --- |
| imports | OK |
| `ruff check .` | All checks passed |
| `mypy app` | Success (77 fichiers) |
| `bandit -r app scripts -q` | 0 issue |
| `pytest` | **292 passed** (+12 vs Phase 13) |
| `coverage` | **90 %** (seuil 85 %) |
| `pip-audit` | No known vulnerabilities found |
| `alembic downgrade base && upgrade head` | réversible 0001 → 0011 |

## 6. Ce qui n'est PAS fait

- **File de revue proactive** (le système propose des réponses à relire — échantillonnage, priorisation par incertitude du modèle) : `list_reviewable` liste tout ; une file gouvernée viendra avec la Phase 15/16.
- **« perf dashboard clinicien »** au sens d'un tableau agrégé : délibérément **non** livré comme vue par clinicien (usage non punitif). `model_quality_report` est le tableau de bord — côté **IA**.
- **Boucle vers l'apprentissage** : les corrections proposées (`EDIT`) et les rejets ne sont pas encore consommés par un pipeline. C'est la Phase 16 (apprentissage continu, sous consentement + revue + double approbation).
- **Frontend `AiReviewCard`** (Next.js, `web/`) : Phase D.
- **`policy_version`** toujours `NULL` : à renseigner quand une réponse portera une version de politique de sortie (OutputSafety) traçable.

## 7. Dette technique / risques résiduels

- `list_reviewable` déchiffre tout l'historique de conversation d'un patient pour le clinicien référent. Justifié pour la revue, mais c'est la première fois que le contenu de conversation est exposé côté clinicien — à garder à l'œil dans le modèle de menace (Phase 18).
- `submit_review` s'appuie sur `IntegrityError` pour la collision (message, relecteur) ; le message d'erreur est traduit en `ConflictError`. Cohérent avec le reste, mais un `SELECT` préalable donnerait un message plus précis (ex. « déjà revu le … »).
- `model_quality_report` charge toutes les revues correspondantes en mémoire pour agréger. Acceptable au volume actuel ; à passer en agrégat SQL (`GROUP BY`) si le corpus grandit.

## 8. Journal de décision

- **D-14.1** — Le « perf dashboard clinicien » de la roadmap est réinterprété en **tableau de bord qualité IA** (`model_quality_report`). Raison : un tableau agrégé par clinicien est structurellement un outil d'évaluation individuelle, contraire au critère « non-usage punitif documenté ». La note de gouvernance formalise ce choix.
- **D-14.2** — La revue exige la relation `ACTIVE`. Raison : cohérence avec la porte unique des Phases 12–13 ; le clinicien référent est déjà responsable du patient.
- **D-14.3** — `FLAG_SAFETY` est un signal, pas un déclencheur. Raison : le moteur de crise reste indépendant de tout jugement en aval (invariant Phase 7/9) ; un clinicien qui signale une réponse douteuse alimente la revue de politique, il ne la modifie pas.
- **D-14.4** — 7 dimensions **toutes** obligatoires. Raison : une évaluation partielle biaise les moyennes ; le coût de saisie (7 curseurs) est acceptable pour une revue ponctuelle et volontaire.

## 9. Critères de sortie — Gate Phase 14

- [x] `APPROVE` / `EDIT` / `REJECT` / `FLAG_SAFETY` ; `EDIT` exige une correction (CHECK + garde).
- [x] Évaluation structurée : 7 dimensions 1-5, toutes requises, validées.
- [x] Catégories de retour (vocabulaire fixe).
- [x] Borné par la relation `ACTIVE` ; `PATIENT` refusé (403) ; unicité (message, relecteur) → 409.
- [x] `FLAG_SAFETY` audité + listé, sans effet automatique sur la politique de crise.
- [x] **Usage non punitif documenté** (`docs/governance/`) **et vérifié** (aucune agrégation par relecteur, sortie sans identifiant de personne, introspection du module).
- [x] `pytest` vert (292) ; couverture 90 % ≥ 85 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible 0001→0011.

## 10. Conclusion

Un clinicien référent peut désormais noter chaque réponse de l'assistant à son
patient, proposer une reformulation, ou lever un drapeau sécurité — et ces
retours **ne peuvent structurellement pas** servir à le juger : le seul tableau
de bord est celui de la qualité de l'**IA**, agrégé par version de modèle. La
prochaine étape est la **Phase 15** (analytics produit vs clinique/IA, gouvernées
séparément, ne lisant que des événements), puis la **Phase 16** (apprentissage
continu) qui consommera enfin les corrections et rejets collectés ici.

STATUS : **PASS**.
