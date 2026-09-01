# PHASE REPORT

Phase : 13 (V2) — Patient 360 + PatientSummaryService + Evidence
Date : 2026-09-01
Objectif : Donner au clinicien une **vue de synthèse** d'un patient suivi, où
**chaque affirmation renvoie à sa source** (un enregistrement réel ouvrable), sans
aucun texte généré par un LLM et sans aucun contenu déchiffré.

STATUS : **PASS** — gate complète verte (280 tests, couverture 90 %).

---

## 1. Analyse

Roadmap audit Phase 13 : « Patient 360 + PatientSummaryService + Evidence
(traçabilité) — chaque affirmation du résumé reliée à sa source, vérifié par
test ». Dépend de la Phase 12 (relation patient–clinicien + timeline).

La v1 n'avait **pas** de service de synthèse — seulement `patient_timeline`
(listes brutes). Le module cible `clinical` (overview-v2 §3) prévoit
« PatientSummaryService + Evidence ». Rien à porter : conception neuve.

Contrainte maître : interdiction de « prétendre que l'IA fournit un diagnostic ».
Une synthèse en texte libre générée par LLM porterait un risque d'hallucination
(affirmation sans source) directement contraire au critère de sortie. D'où le
choix d'une synthèse **déterministe et gabaritée**.

## 2. Conception

| Décision | Choix |
| --- | --- |
| Génération | **Zéro LLM.** Chaque `SummaryStatement` est produit par un gabarit déterministe sur des données numériques / métadonnées. Aucune phrase n'est possible sans enregistrement source. |
| Traçabilité | Chaque `SummaryStatement` porte `evidence: tuple[Evidence, ...]` **non vide** (invariant dur : `build_summary` lève si un énoncé sort sans pièce). `Evidence(type, id)` où `type` ∈ 8 tables réelles. `resolve_evidence(patient_id, evidence)` renvoie un descriptif **non sensible** de la ligne **après avoir vérifié qu'elle appartient au patient** — `None` si la traçabilité est cassée (mauvais patient, id inconnu). |
| Contenu | Jamais de contenu déchiffré : pas de message de conversation, pas de contenu de mémoire, pas de réponse brute au questionnaire. Uniquement scores, bandes de sévérité, comptes, dates, `provenance`, `purpose`. |
| Formulation | Corrélationnelle : « en hausse de +2 points », « score maximal 0.82 (corrélation — pas un verdict) », « signal de sûreté à explorer ». Test anti-diagnostic (`diagnostic`, `souffre de`, `atteint de`, …). `DISCLAIMER` explicite toujours joint. |
| Énoncés conditionnels | `phq9.trend` seulement avec ≥ 2 questionnaires ; `phq9.item9` seulement si item 9 ≥ 1 ; chaque bloc absent si la table est vide (patient neuf ⇒ `statements == ()` + disclaimer). |
| Patient 360 | `clinician.patient_360` = identité + consentements (`consent.list_for_user`) + synthèse tracée + objectifs + timeline (réutilise `patient_timeline` de la Phase 12). Une seule porte : `require_active_relationship`. |
| Persistance | Aucune. Synthèse **calculée à la lecture** — pas de table, pas de migration. Un instantané immuable versionné pourra venir plus tard (reproductibilité), il n'est pas requis pour la traçabilité qui est entièrement testable sur la sortie calculée. |

### Énoncés produits

| `key` | catégorie | source(s) |
| --- | --- | --- |
| `phq9.latest` | assessment | dernier `phq9_assessments` |
| `phq9.trend` | assessment | 2 derniers `phq9_assessments` |
| `phq9.item9` | safety | dernier `phq9_assessments` (si item 9 ≥ 1) |
| `alerts.open` | safety | toutes les `alerts` en cours du patient |
| `risk.recent` | risk | `risk_assessments` des 7 derniers jours |
| `goals.active` | goals | `goals` actifs + dernier `goal_progress` |
| `engagement.activity` | engagement | `conversations` (5 plus récentes en pièces) — volume seul |
| `context.memory` | engagement | `memories` `ACTIVE` — comptes par provenance, contenu jamais exposé |
| `consent.active` | consent | `consents` non révoqués |

## 3. Implémentation — fichiers

| Fichier | Rôle |
| --- | --- |
| `app/application/patient_summary.py` (nouveau) | `Evidence`, `SummaryStatement`, `PatientSummary`, `build_summary`, `resolve_evidence`, `DISCLAIMER`. |
| `app/application/clinician.py` | `patient_summary_for` (synthèse + garde relation), `patient_360` (bundle + garde relation). |
| `app/api/clinician.py` | `GET /patients/{id}/summary`, `GET /patients/{id}/360`, `GET /patients/{id}/evidence/{type}/{id}` (résout une pièce, 404 si non rattachée au patient). |
| `tests/test_patient_summary.py` (nouveau) | 10 tests. |

Pas de migration (0010 reste la tête). Pas de nouveau modèle.

## 4. Invariants vérifiés

| Invariant | Test |
| --- | --- |
| **Chaque énoncé a ≥ 1 pièce justificative, et chacune se résout vers une source réelle du patient** | `test_patient_summary::test_every_statement_is_backed_by_resolvable_evidence` |
| Une pièce d'un autre patient (même id) ou un id inconnu ne se résout pas | `::test_evidence_of_another_patient_does_not_resolve` |
| Formulation corrélationnelle, jamais diagnostique ; disclaimer toujours présent | `::test_summary_is_correlational_never_diagnostic` |
| Aucun contenu déchiffré (mémoire, message, réponses brutes) dans la synthèse ni le 360 | `::test_summary_never_carries_decrypted_content`, `::test_patient_360_bundles_...` (canary `SECRET-CANARY`) |
| `phq9.trend` conditionné à ≥ 2 questionnaires ; `phq9.item9` à item 9 ≥ 1 | `::test_item9_and_trend_statements_are_conditional` |
| Patient neuf ⇒ `statements == ()` + disclaimer | `::test_empty_patient_yields_only_the_disclaimer` |
| Patient 360 exige la relation `ACTIVE` (403 sinon) ; bundle synthèse + consentements + objectifs + timeline | `::test_patient_360_requires_a_relationship`, `::test_patient_360_bundles_...` |
| `PATIENT` ne peut lire ni `/summary` ni `/360` (403) | `::test_patient_cannot_read_a_summary` |
| Bout-en-bout HTTP : le clinicien lit la synthèse puis **ouvre chaque pièce justificative** (200) | `::test_clinician_reads_summary_then_opens_each_evidence` |

## 5. Résultats de vérification (image `server`, PG + Redis + Mailpit)

| Contrôle | Résultat |
| --- | --- |
| imports (`app.main`, `app.workers.scheduler`) | OK |
| `ruff check .` | All checks passed |
| `mypy app` | Success (75 fichiers) |
| `bandit -r app scripts -q` | 0 issue |
| `pytest` | **280 passed** (+10 vs Phase 12) |
| `coverage` | **90 %** (seuil 85 %) |
| `pip-audit` | No known vulnerabilities found |
| `alembic downgrade base && upgrade head` | réversible 0001 → 0010 |

## 6. Ce qui n'est PAS fait

- **Instantané de synthèse persisté / versionné** : la synthèse est recalculée à chaque lecture. Un `patient_summaries` immuable (lignée reproductible, comparaison dans le temps) est une itération ultérieure.
- **Résumé narratif** (paragraphe rédigé) : délibérément non — le risque d'affirmation sans source l'emporte. Les énoncés sont atomiques et tracés ; la mise en récit relève de l'UI (Phase D) ou d'un LLM sous contrainte de citation stricte, plus tard.
- **Contenu de mémoire / de conversation dans le 360** : hors périmètre — nécessiterait un accès déchiffré explicitement audité, décision produit à part.
- **Frontend Patient 360** (Next.js, `web/`) : Phase D.
- **`risk.recent` sur > 7 jours / agrégats de tendance longue** : `longitudinal_snapshots` (déjà en base) pourra alimenter un énoncé `context.longitudinal` quand le worker de précalcul (§78) sera câblé.

## 7. Dette technique / risques résiduels

- `resolve_evidence` fait une requête par pièce ; l'endpoint `evidence/{type}/{id}` en résout une seule. Pour l'UI, un endpoint batch serait plus efficace.
- `build_summary` enchaîne plusieurs requêtes séquentielles (une par bloc). Acceptable pour une lecture ponctuelle de dossier ; à regrouper si la synthèse devient un affichage de liste.
- Le `# type: ignore[attr-defined]` sur `select(model).where(model.id == …)` dans `resolve_evidence` : accès dynamique par table, les modèles n'exposent pas `id` sur `Base`. Contenu, pas contournable proprement sans registre typé.

## 8. Journal de décision

- **D-13.1** — Synthèse déterministe gabaritée, zéro LLM. Raison : le critère de sortie (« chaque affirmation reliée à sa source ») est incompatible avec un texte libre génératif ; un gabarit ne peut structurellement pas halluciner.
- **D-13.2** — `resolve_evidence` vérifie l'appartenance au patient. Raison : la traçabilité doit être **prouvable** — une pièce qui pointe vers la ligne d'un autre patient est une fuite, pas une source.
- **D-13.3** — Aucune persistance en Phase 13. Raison : la valeur (traçabilité) est atteinte sans table ; un instantané immuable ajoute des contraintes (révocation de mémoire → l'instantané doit-il être réécrit ?) à trancher séparément.
- **D-13.4** — La mémoire n'apparaît qu'en comptes (provenance), jamais en contenu. Raison : le contenu de mémoire est du texte patient chiffré ; l'exposer dans une vue clinicien élargit fortement la surface de donnée sensible pour un bénéfice de synthèse faible.

## 9. Critères de sortie — Gate Phase 13

- [x] `PatientSummaryService` : synthèse déterministe, énoncés atomiques catégorisés.
- [x] **Evidence** : chaque énoncé porte ≥ 1 pièce ; `resolve_evidence` prouve l'appartenance au patient ; test qui ouvre **toutes** les pièces de **tous** les énoncés.
- [x] Jamais de diagnostic ; disclaimer joint ; test anti-formulation.
- [x] Jamais de contenu déchiffré (canary mémoire + message).
- [x] Patient 360 : bundle borné par la relation `ACTIVE` ; `PATIENT` refusé (403).
- [x] `pytest` vert (280) ; couverture 90 % ≥ 85 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migrations réversibles 0001→0010.

## 10. Conclusion

Le clinicien dispose d'une synthèse où **rien n'est affirmé sans preuve** : chaque
ligne du résumé se déplie vers l'enregistrement qui la justifie, vérifié
patient par patient, et aucun contenu sensible déchiffré n'y transite. La
formulation reste corrélationnelle et explicitement non diagnostique. La
prochaine étape est la **Phase 14** (Clinician AI Review : APPROVE / EDIT /
REJECT / FLAG + évaluation structurée 1–5), qui réutilisera la relation et
l'audit posés en Phases 12–13.

STATUS : **PASS**.
