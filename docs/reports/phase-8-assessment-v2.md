# PHASE REPORT

Phase : 8 (V2) — PHQ-9 / auto-évaluation
Date : 2026-09-01
Objectif : Instrument PHQ-9 versionné, scoring avec **item 9 isolé** comme signal de sûreté, historique, tendance, rappels, contrôle d'accès. La bande de sévérité alimente le contexte de personnalisation.

STATUS : **PASS**.

---

## 1. Livré

### Domaine (`app/domain/assessment/phq9.py`) — porté de v1
`PHQ9_VERSION`, `Phq9Result` (`total_score`, `item9_score`, `severity_band`), `score(answers)` (9 entiers 0-3, booléens rejetés), `severity_band(total)` — seuils **publiés de Kroenke, Spitzer & Williams 2001** : `minimale` ≤4, `légère` ≤9, `modérée` ≤14, `modérément sévère` ≤19, `sévère` ≤27. Repères configurables, pas des décisions médicales (§136).

### Schéma (`0007_phq9`)
- `phq9_assessments` (réponses **chiffrées**, `total_score` 0-27, `item9_score` 0-3), RLS.
- `assessment_reminders` (instrument, `due_at`, statut), RLS.
- **`alerts` généralisé** : `crisis_event_id` devient nullable ; `source` (`MESSAGE`/`ASSESSMENT`) ; `assessment_id` nullable FK ; CHECK `ck_alert_has_trigger` (au moins un déclencheur). `downgrade` complet.

### Application (`app/application/assessment.py`)
- `submit_phq9` : score → persiste → **si item 9 ≥ seuil ou score total ≥ seuil, escalade**.
- `_alert_level` : seuils depuis `policy.phq9_alert` (versionné) — `item9 ≥ 2 → RED` ; `item9 ≥ 1` **ou** `total ≥ 20 → ORANGE`.
- `EscalationEngine.escalate_assessment` : alerte `source=ASSESSMENT`, clé d'idempotence `phq9:{assessment_id}`, **même cycle de vie / SLA / notification** qu'une alerte de message.
- `history`, `trend` (delta + direction `improving`/`worsening`/`stable` — corrélation, jamais un diagnostic §58), `latest_severity_band`, `answers_for` (propriétaire uniquement), `schedule_reminder` / `list_reminders`.

### API (`app/api/assessment.py`)
`POST /api/v1/assessments/phq9` (limite 20/h, 6/h en test) · `GET .../phq9` (historique) · `GET .../phq9/trend` · `GET .../phq9/{id}/answers` · `POST /reminders` · `GET /reminders`.

### Intégration
`ConversationOrchestrator._build_context` ajoute `phq9_severity_band` (best-effort). `ai/prompt.build_messages` l'insère comme **contexte interne** avec instruction explicite de ne jamais le mentionner ni citer de chiffre (TV-02 : le score brut ne part jamais dans un prompt).

## 2. Invariants vérifiés

| Invariant | Test |
| --- | --- |
| Item 9 isolé et conservé séparément du total | `test_score_totals_and_isolates_item9` |
| Scoring rejette longueur/plage/booléens invalides | `test_score_rejects_malformed_answers`, `test_score_rejects_booleans`, `test_out_of_range_answer_is_400` |
| Bandes de sévérité = seuils publiés | `test_severity_bands_match_published_thresholds` (10 bornes) |
| Item 9 ≥ 2 → alerte RED `source=ASSESSMENT` ; item 9 = 1 → ORANGE ; total ≥ 20 sans item 9 → ORANGE | `test_item9_two_or_more_opens_a_red_alert`, `test_item9_one_opens_an_orange_alert`, `test_high_total_without_item9_opens_an_orange_alert` |
| PHQ-9 calme → aucune alerte | `test_calm_phq9_persists_without_an_alert`, `test_moderate_total_without_item9_does_not_alert` |
| Réponses chiffrées au repos | `test_answers_are_encrypted_at_rest` |
| Historique / tendance propres à l'utilisateur ; réponses d'autrui → 404 ; isolation inter-organisation | `test_history_is_own_only`, `test_assessments_are_isolated_between_organizations` |
| Bande de sévérité dans le prompt, **jamais le score brut** | `test_severity_band_is_woven_into_the_prompt_never_the_raw_score` |
| Soumission rate-limitée | `test_submission_is_rate_limited` |
| Rappel dans le passé rejeté | `test_past_reminder_is_rejected` |

## 3. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **198 tests** (166 + 32 Phase 8), ~54 s |
| `coverage` | **90 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001→0007) |

## 4. Ce qui n'est PAS fait

- **Vue clinicien** des PHQ-9 d'un patient : pas de table relation patient-clinicien en V2 encore (Phase 12) — l'accès est patient-uniquement pour l'instant, documenté.
- **Envoi effectif des rappels** : la table + la planification existent ; le worker qui les envoie est Phase 10 (notifications).
- **Autres instruments** (GAD-7, etc.) : l'architecture (`instrument_version`, `assessment_reminders.instrument`) le permet ; hors périmètre.
- **Graphe de tendance** : `trend` renvoie les données ; la visualisation est frontend / Patient 360 (Phase 13).
- Le passage d'un `total ≥ 20` en RED (plutôt qu'ORANGE) : choix de politique laissé au comité clinique — actuellement seul l'item 9 déclenche RED.

## 5. Critères de sortie — Gate Phase 8

- [x] PHQ-9 versionné, scoring, item 9 isolé.
- [x] Historique + tendance.
- [x] Rappels (planification, liste).
- [x] Contrôle d'accès : propriétaire uniquement, isolation org.
- [x] Item 9 positif / score élevé → alerte via le même `EscalationEngine` (SLA, notification, cycle de vie).
- [x] Bande de sévérité qualitative dans le contexte de conversation, jamais le score brut.
- [x] `pytest` vert (198) ; couverture 90 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible (0001→0007).

## 6. Conclusion

Le PHQ-9 n'est pas un simple formulaire : un item 9 positif ou un score élevé entre dans **le même flux d'alerte gouverné** que la détection de crise sur un message — persistance transactionnelle, SLA, notification, revue humaine — au lieu d'attendre qu'un clinicien consulte un tableau de bord. La bande de sévérité influence subtilement le ton de la conversation sans jamais exposer le chiffre. La **Phase 9** approfondit le moteur de risque/crise (modèle entraîné, robustesse) ; la **Phase 10** ajoute les canaux de notification réels et le worker de rappels.

STATUS : **PASS**.
