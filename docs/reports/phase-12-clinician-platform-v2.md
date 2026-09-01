# PHASE REPORT

Phase : 12 (V2) — Plateforme clinicien (surface API)
Date : 2026-09-01
Objectif : Donner au clinicien un accès **gouverné** au suivi de ses patients —
Today's Overview, Patient List, Alert Center, timeline patient, actions sur
alerte — le tout borné par une relation `ACTIVE` patient–clinicien créée par un
administrateur. Phase 11 (voix temps réel) reste différée (décision D-3).

STATUS : **PASS** — gate complète verte (270 tests, couverture 89 %).

---

## 1. Analyse

v1 (`backend/app/clinician.py`, 143 loc) portait déjà : `patient_clinician_relationships`,
`create/end_relationship`, `has_active_relationship`, `list_patients_for_clinician`,
`patient_timeline`, `list_alerts_for_clinician`, `act_on_alert`. Le catalogue RBAC
V2 (migration `0001`) **anticipait** cette phase : permissions `clinician.dashboard.read`,
`clinician.patient.read`, `alert.act`, `admin.relationships.manage` ; rôles
`PSYCHOLOGIST` / `CLINICAL_SUPERVISOR` déjà dotés. Le modèle `Alert` avait déjà
`assigned_clinician_id` + l'index `ix_alerts_assignee`. Il manquait : la table de
relations, la couche application async, les endpoints, et le câblage de l'action
clinicien sur la transition atomique d'alerte (Phase 9).

Le frontend (Next.js `web/`, WCAG, tests d'ergonomie) relève de la **Phase D** du
prompt maître (frontend traité séparément, écran par écran) et n'est pas dans ce
périmètre : Phase 12 livre la **surface API**, comme les phases 2–10.

## 2. Conception

| Décision | Choix |
| --- | --- |
| Porte d'accès | **Une seule** : `relationships.require_active_relationship(clinician_id, patient_id)`. Pas de relation `ACTIVE` ⇒ 403. Appelée par chaque accès nominatif (timeline, action sur alerte) ; les listes filtrent par sous-requête `patient_id IN (relations actives)`. |
| Qui crée les relations | `ADMIN` / `SUPER_ADMIN` (`admin.relationships.manage`). Un clinicien ne s'auto-attribue jamais un patient. |
| Validation | `create_relationship` vérifie que la cible « patient » porte bien le rôle `PATIENT` et la cible « clinicien » `PSYCHOLOGIST`/`CLINICAL_SUPERVISOR` (409 sinon), que les deux comptes existent et sont actifs dans l'organisation (404 sinon), patient ≠ clinicien. Idempotent (au plus une relation `ACTIVE` par couple — index partiel unique). |
| Action sur alerte | `alerts.act_on_alert` : vérifie la relation, puis délègue à `transition_alert` (transition atomique `UPDATE … WHERE status=<lu>` de la Phase 9). Le perdant d'une course reçoit un **409** (`ConflictError`), une transition invalide un **400**. Première prise en charge ⇒ `assigned_clinician_id` posé **dans le même UPDATE atomique** (`assign_to`, uniquement si encore vide). |
| Contenu exposé | Timeline = historique + tendance PHQ-9 (score total, bande de sévérité, **item 9** comme signal de sûreté isolé), alertes, actions d'alerte. **Jamais** le contenu des conversations, **jamais** les réponses brutes item par item du questionnaire. |
| Multi-tenant | Table `patient_clinician_relationships` avec RLS `FORCE` + politique tenant (même patron que les 9 tables précédentes). |

## 3. Implémentation — fichiers

| Fichier | Rôle |
| --- | --- |
| `app/alembic/versions/0010_clinician.py` | Table `patient_clinician_relationships` (RLS forcée + politique), index partiel unique `uq_pcr_active` sur `(patient_id, clinician_id) WHERE status='ACTIVE'`, index `ix_pcr_clinician` / `ix_pcr_patient`. Réversible. |
| `app/infrastructure/models.py` | Modèle `PatientClinicianRelationship` (CHECK `status IN ('ACTIVE','ENDED')`). |
| `app/application/relationships.py` (nouveau) | `create_relationship` (validation rôles + idempotence), `end_relationship`, `has_active_relationship`, `require_active_relationship`, `list_relationships`. Audit sur création / rupture (métadonnées : ids seulement, aucune donnée clinique). |
| `app/application/clinician.py` (nouveau) | `overview` (Today's Overview : patients suivis, alertes ouvertes ORANGE/RED, SLA dépassés, file assignée au clinicien), `list_patients` (dernier PHQ-9 + nb d'alertes ouvertes, trié par urgence), `list_alerts` (Alert Center, filtres `level`/`status` validés), `patient_timeline`, `alert_row`. |
| `app/application/alerts.py` | `act_on_alert` (relation + transition atomique + assignation + audit `alert.act`) ; `transition_alert` gagne un paramètre `assign_to` optionnel. `CLINICIAN_ACTIONS` = `{ACKNOWLEDGED, IN_REVIEW, ESCALATED, RESOLVED, CANCELLED}` (`NOTIFIED`/`CLOSED` restent systèmes). |
| `app/api/clinician.py` (nouveau) | Router `/api/v1/clinician` : `GET /overview`, `GET /patients`, `GET /patients/{id}/timeline`, `GET /alerts`, `POST /alerts/{id}/actions`. `require_role(PSYCHOLOGIST, CLINICAL_SUPERVISOR)` sur chaque route. |
| `app/api/admin.py` | `GET/POST /api/v1/admin/relationships`, `DELETE /api/v1/admin/relationships/{id}` (`ADMIN`/`SUPER_ADMIN`). |
| `app/api/schemas.py` | `RelationshipCreateRequest`, `RelationshipItem`, `AlertActionRequest`. |
| `app/main.py` | Router `clinician` inclus. |
| `tests/conftest.py` | `patient_clinician_relationships` ajouté à `_CLEAN_ORDER`. |
| `tests/test_relationships.py` (nouveau) | 10 tests. |
| `tests/test_clinician.py` (nouveau) | 10 tests. |

## 4. Invariants vérifiés

| Invariant | Test |
| --- | --- |
| Pas de relation `ACTIVE` ⇒ pas de lecture de dossier (403) | `test_clinician::test_timeline_requires_an_active_relationship` |
| Pas de relation `ACTIVE` ⇒ pas d'action sur alerte (403) | `test_clinician::test_act_on_alert_denied_without_relationship` |
| Listes bornées aux patients suivis (un patient non suivi, avec alerte, reste invisible) | `test_clinician::test_lists_are_scoped_to_followed_patients` |
| Overview ne compte que la file du clinicien courant | `test_clinician::test_overview_counts_only_this_clinicians_queue` |
| Timeline sans contenu de conversation ni réponses brutes au questionnaire | `test_clinician::test_timeline_never_carries_conversation_content_or_raw_answers` |
| Action clinicien = transition atomique : un seul gagnant en course, le perdant a un 409 | `test_clinician::test_concurrent_acks_have_exactly_one_winner` |
| Transition invalide ⇒ 400 ; assignation posée à la première prise en charge | `test_clinician::test_act_on_alert_rejects_an_invalid_transition`, `::test_act_on_alert_acknowledges_assigns_and_audits` |
| `PATIENT` n'atteint jamais `/api/v1/clinician/*` ni `/api/v1/admin/relationships` (403) | `test_clinician::test_patient_cannot_reach_clinician_endpoints`, `test_relationships::test_admin_relationship_endpoint_requires_privilege` |
| Création de relation : rôle cible validé, idempotente, isolée par organisation | `test_relationships::test_create_rejects_a_non_patient_or_non_clinician`, `::test_create_is_idempotent`, `::test_relationships_are_isolated_between_organizations` |
| Rupture ferme la porte ; re-création possible ensuite | `test_relationships::test_end_relationship_closes_the_gate`, `::test_ending_then_recreating_is_allowed` |
| Chaque changement de relation est audité (ids seulement) | `test_relationships::test_audit_records_the_relationship_change` |
| Bout-en-bout HTTP (login clinicien MFA → overview → patients → alerts → action → timeline) | `test_clinician::test_clinician_http_happy_path` |

## 5. Résultats de vérification (image `server`, PG + Redis + Mailpit)

| Contrôle | Résultat |
| --- | --- |
| `python -c 'import app.main; import app.workers.scheduler'` | OK |
| `ruff check .` | All checks passed |
| `mypy app` | Success: no issues found in 76 source files |
| `bandit -r app scripts -q` | 0 issue |
| `pytest` | **270 passed** (+20 vs Phase 10) |
| `coverage` | **89 %** (seuil 85 %) |
| `pip-audit` | No known vulnerabilities found |
| `alembic downgrade base && alembic upgrade head` | réversible 0001 → 0010 |

## 6. Ce qui n'est PAS fait

- **Frontend clinicien** (Next.js `web/`, WCAG, tests d'ergonomie) : Phase D du prompt maître, hors périmètre ici.
- **AI Review Center** (APPROVE / EDIT / REJECT / FLAG, évaluation structurée 1–5) : Phase 14.
- **Analytics produit + clinique/IA, AI quality dashboard** : Phase 15.
- **Notification temps réel au clinicien à l'ouverture d'une alerte dans le dashboard** (websocket / SSE côté clinicien) : dépend du frontend ; l'e-mail « connectez-vous » de la Phase 10 reste le canal.
- **Réassignation explicite d'une alerte** entre cliniciens : seul le premier `ACKNOWLEDGED` pose `assigned_clinician_id` ; un transfert de file est une itération produit ultérieure.
- **Vue superviseur cross-clinicien** (`CLINICAL_SUPERVISOR` voit aujourd'hui exactement comme un `PSYCHOLOGIST`, borné à ses propres relations) : à préciser avec le besoin métier.

## 7. Dette technique / risques résiduels

- `list_patients` fait une requête par patient (dernier PHQ-9 + compte d'alertes) — acceptable pour des files de quelques dizaines de patients, à passer en agrégat unique si la taille grandit.
- `require_active_relationship` est une vérification applicative en plus du RLS ; elle n'est pas rejouée au niveau base. Un accès direct SQL (hors application) contournerait la relation mais pas le RLS d'organisation — cohérent avec le modèle de menace (l'application est le point de contrôle métier).
- `transition_alert` lève toujours `ValueError` ; `act_on_alert` le traduit en `ConflictError`/`DomainError`. Les autres appelants (`sla_sweep`, `mark_notified`) attrapent toujours `ValueError` — inchangé.

## 8. Journal de décision

- **D-12.1** — La création de relation est réservée à l'`ADMIN`, pas au clinicien. Raison : éviter l'auto-attribution d'un patient ; tracer qui a ouvert l'accès.
- **D-12.2** — L'assignation (`assigned_clinician_id`) est posée automatiquement au premier `ACKNOWLEDGED`, dans le même UPDATE atomique. Raison : un seul clinicien « propriétaire » sans étape séparée susceptible de générer une course.
- **D-12.3** — La timeline expose l'item 9 (score isolé) mais jamais les réponses brutes. Raison : l'item 9 est un signal de sûreté que le clinicien doit voir ; le détail item par item n'apporte rien de clinique ici et élargit la surface de donnée sensible.
- **D-12.4** — Surface API seulement ; le frontend reste Phase D. Raison : cohérence avec les phases 2–10 et le découpage du prompt maître.

## 9. Critères de sortie — Gate Phase 12

- [x] Table de relations patient–clinicien (RLS forcée, index partiel unique, réversible).
- [x] Création / rupture par un admin, avec validation des rôles et idempotence.
- [x] `require_active_relationship` : porte d'accès unique, deny-by-default, testée sur lecture ET action.
- [x] Alert Center + Patient List + Today's Overview bornés aux patients suivis.
- [x] Action clinicien sur alerte via la transition atomique (un gagnant en course, 409 pour le perdant).
- [x] `PATIENT` refusé sur toute la surface clinicien / admin-relations (403).
- [x] Aucun contenu de conversation ni réponse brute de questionnaire dans la timeline.
- [x] `pytest` vert (270) ; couverture 89 % ≥ 85 % ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; migration réversible 0001→0010.

## 10. Conclusion

Un clinicien voit désormais **exactement** les patients qu'un administrateur lui a
confiés, et rien d'autre : son tableau de bord (compteurs, file d'alertes, liste
de patients), le dossier longitudinal d'un patient suivi (PHQ-9 + alertes +
historique d'actions, sans contenu de conversation), et il agit sur une alerte
par la même transition atomique et auditée que le reste du cycle de vie. La
prochaine étape est la **Phase 13** (portage `learning` : feedback d'apprentissage
avec consentement + revue humaine + double approbation), puis la **Phase 14**
(Clinician AI Review).

STATUS : **PASS**.
