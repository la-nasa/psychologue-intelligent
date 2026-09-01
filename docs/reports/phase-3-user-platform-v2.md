# PHASE REPORT

Phase : 3 (V2) — Plateforme utilisateur
Date : 2026-09-01
Objectif : Compléter l'expérience compte : enrôlement MFA, consentement **versionné et révocable** (6 finalités dont `AI_EXTERNAL` et `VOICE`), profil étendu + préférences de communication, onboarding, demande de suppression de compte. Contrôles d'accès BOLA/IDOR et isolation inter-organisation vérifiés.

STATUS : **PASS** — `docker compose` + `pytest` verts, isolation et invariants testés.

---

## 1. Livré

### Schéma (`0003_user_platform`)
5 tables : `consent_versions` (globale, seed des 6 finalités en version « 1 »), `consents`, `profiles`, `communication_preferences`, `deletion_requests` — les 4 dernières avec `organization_id` + **RLS `FORCE`** (ADR-008). `downgrade` complet, réversibilité vérifiée (0001+0002+0003).

### Application
- `application/consent.py` — `grant` (résout la version courante, ré-active si révoquée à la même version au lieu de dupliquer), `revoke` (toutes les décisions actives de la finalité), **`has_active_consent`** (point de contrôle pour Phase 4 / Phase 16), `list_for_user`, `current_version`.
- `application/profile.py` — `get/save_profile` (`about_me` **chiffré au repos** — TV-03 ; onboarding horodaté **une seule fois**, jamais réécrit), `get/save_preferences`.
- `application/account.py` — `request_deletion` (enregistre `OPEN`, idempotent — n'efface pas les traces d'audit).
- `application/mfa.py` — `enroll` (génère un secret, le stocke chiffré, **n'active pas**), `activate` (vérifie un code TOTP puis `mfa_enabled = true`). URI `otpauth://` de provisionnement.

### API
`GET/POST /api/v1/profile` · `GET/PUT /api/v1/profile/preferences` · `GET /api/v1/consents` · `POST /api/v1/consents` · `POST /api/v1/consents/revoke` · `POST /api/v1/auth/mfa/enroll` · `POST /api/v1/auth/mfa/activate` · `POST /api/v1/privacy/deletion-requests`. OpenAPI généré (~14 opérations).

### Déploiement
`scripts/bootstrap.py` étendu : les comptes de rôle clinique (`ADMIN`, `SUPER_ADMIN`, `PSYCHOLOGIST`, `CLINICAL_SUPERVISOR`) reçoivent un **premier secret MFA activé**, imprimé une fois — résout le blocage œuf-poule (un clinicien ne peut ni se connecter sans MFA active, ni s'enrôler sans jeton).

## 2. Contrôles d'accès vérifiés (gate BOLA/IDOR + cross-tenant)

| Test | Vérifie |
| --- | --- |
| `test_consent.py::test_consents_are_isolated_between_organizations` | un jeton org B ne voit aucun consentement d'org A |
| `test_profile.py::test_profile_is_isolated_between_organizations` | idem pour le profil |
| `test_mfa.py::test_mfa_enroll_requires_authentication` / `test_privacy.py::test_deletion_request_requires_auth` | endpoints protégés |
| `test_consent.py::test_unknown_purpose_is_rejected_by_schema` / `test_profile.py::test_invalid_preference_value_is_rejected` | validation stricte, pas d'injection de valeur d'énum |
| toutes les opérations passent par `principal.user_id` (dérivé du jeton), jamais un id du corps | pas de BOLA horizontal |

## 3. Invariants

- **Consentement révocable, versionné** : `test_grant_then_list_then_revoke`, `test_regranting_same_version_reactivates_not_duplicates`, `test_all_six_purposes_are_grantable`. `has_active_consent` suit grant/revoke (`test_has_active_consent_helper_tracks_grant_and_revoke`).
- **`about_me` jamais en clair en base** : `test_about_me_is_encrypted_at_rest` lit la colonne et vérifie l'absence du texte.
- **Onboarding horodaté une seule fois** : `test_default_profile_then_save_stamps_onboarding_once`.
- **MFA : enrôlement puis activation** : `test_patient_can_enroll_and_activate_mfa`, activation avant enrôlement rejetée, double enrôlement après activation → 409, clinicien provisionné se connecte avec TOTP et échoue avec un mauvais code.
- **Demande de suppression idempotente** : une seule ligne `OPEN` par utilisateur.

## 4. Résultats de vérification

| Contrôle | Résultat |
| --- | --- |
| `pytest` | **79 tests** (52 + 27 Phase 3) |
| `coverage report` | **91 %** (seuil 85 %) |
| `ruff` / `mypy` / `bandit` / `pip-audit` | propres |
| `alembic downgrade base && upgrade head` | réversible (0001+0002+0003) |

**Dette de test** : la suite passe désormais ~3 min 40 (NullPool = une connexion par opération, Argon2, `TRUNCATE` avant chaque test). À optimiser plus tard (boucle d'événements de session + pool, ou base par worker `pytest-xdist`). Un piège découvert : les tests qui passent par le transport ASGI in-process sous-comptent la couverture des instructions situées **après un `await`** dans les handlers — d'où des tests unitaires à appel direct pour les modules `application/*` (`test_user_platform_units.py`).

## 5. Ce qui n'est PAS fait

- **Export de données personnelles** (portabilité RGPD) : la demande de suppression existe ; un export structuré est un ajout Phase 21 (préparation étude / conformité).
- **Traitement effectif d'une demande de suppression** (anonymisation, purge selon rétention) : hors périmètre logiciel à ce stade (`production-readiness`).
- **Écran de consentement `AI_EXTERNAL`** nommant le fournisseur, le pays de traitement, la rétention : le backend gère la finalité ; le texte et l'UI viennent avec le frontend (Phase 3 front / Phase 4).
- **Récupération de compte / reset MFA par un admin** : Phase 12 (console clinicien/admin).
- **v1 intacte** : `backend/`, `frontend/` non touchés.

## 6. Critères de sortie — Gate Phase 3

- [x] Enrôlement + activation MFA ; clinicien provisionné peut se connecter.
- [x] Consentement versionné, révocable, 6 finalités (`CARE`, `LEARNING`, `AI_EXTERNAL`, `VOICE`, `ANALYTICS`, `RESEARCH`).
- [x] Profil étendu (`display_name`, `about_me` chiffré, `language`) + préférences de communication.
- [x] Onboarding horodaté une seule fois.
- [x] Demande de suppression de compte, idempotente.
- [x] Isolation inter-organisation vérifiée sur consentement et profil.
- [x] Contrôles d'accès (auth requise, validation stricte, pas de BOLA).
- [x] Migration réversible ; `ruff`/`mypy`/`bandit`/`pip-audit` propres ; couverture ≥ 85 %.

## 7. Conclusion

La plateforme utilisateur V2 est fonctionnelle et gouvernée : le consentement est la brique que le moteur de conversation (Phase 4) interrogera avant de router un message (`CARE` pour converser, `AI_EXTERNAL` pour le chemin DEEP externe — ADR-007). La **Phase 4** est la prochaine : moteur de conversation, streaming, `ConversationOrchestrator`, et premier consommateur HTTP réel du pipeline de sûreté porté en Phase B.

STATUS : **PASS**.
