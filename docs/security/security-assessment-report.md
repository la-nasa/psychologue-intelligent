# Security Assessment Report — Psychologue Intelligent

Date: 2026-08-27
Auditeur: Claude Code (agent), sur autorisation explicite de l'utilisateur, périmètre limité à ce dépôt
Méthodologie: OWASP Top 10, OWASP ASVS, OWASP API Security Top 10, CWE, STRIDE — voir Section « Methodology »

## Executive Summary

Un audit méthodique du dépôt a été mené à travers 30+ catégories de vulnérabilités. La majorité des catégories du prompt d'audit ne s'appliquent pas à cette application (pas de paiement, pas d'upload de fichier, pas de JWT, pas de Docker, pas de webhooks, pas de XML, pas de service tiers) — ce n'est pas une lacune d'audit, c'est une surface d'attaque réellement réduite, vérifiée par lecture du code, pas supposée. Dans les catégories applicables, **2 vulnérabilités réelles et exploitables ont été trouvées, reproduites de manière déterministe, corrigées, et re-testées** : une race condition (TOCTOU) permettant de contourner l'invariant de sécurité « un rejet clinique bloque définitivement un modèle », et l'absence totale d'en-têtes de sécurité Content-Security-Policy/Strict-Transport-Security/Permissions-Policy. Une incohérence de rate limiting (PHQ-9 non protégé alors que l'endpoint de message l'était) a également été fermée. Aucune vulnérabilité Critical résiduelle n'a été trouvée après correction et second passage.

## Scope

Dépôt local `Psychologue Intelligent` : `backend/`, `frontend/`, `ml/`, `scripts/`, `tests/`, `config/`, `.github/workflows/`. Aucun système tiers, aucune infrastructure cloud, aucun compte externe n'a été ciblé (aucun n'existe pour ce projet à ce stade — voir `docs/deployment/production-readiness.md`).

## Architecture

Monolithe modulaire Python, bibliothèque standard uniquement en exécution, SQLite (connexion par requête), trois frontends statiques vanilla JS. Frontière de confiance principale : Client ↔ API HTTP (jeton `Bearer` opaque). Aucune frontière réseau vers un tiers (vérifié par grep : zéro appel `urllib.request`/`requests`/`httpx` dans `backend/`). Détail complet : `docs/architecture/overview.md`, `docs/reports/final-report.md` Section 2.

## Threat Model

Voir `docs/security/threat-model.md` (13 menaces STRIDE/OWASP tracées à des tests), complété par cet audit avec SEC-001, SEC-002, SEC-003 ci-dessous.

## Methodology

1. Reconnaissance exhaustive du dépôt (grep systématique par catégorie : secrets, désérialisation, XML, SSRF, upload, CORS, headers).
2. Réutilisation et vérification des contrôles déjà en place (suite `test_security.py` existante, `bandit`, `pip-audit`, `scan_secrets.py`) plutôt que re-découverte à l'identique.
3. Recherche ciblée dans les catégories non encore couvertes : logique métier, race conditions, en-têtes de sécurité, cohérence du rate limiting.
4. Pour chaque piste : reproduction déterministe avant toute correction (pas de vulnérabilité déclarée sur la seule foi d'un scanner ou d'une intuition).
5. Correction à la cause racine, test de régression permanent, re-test complet.
6. Second passage adversarial contre les corrections elles-mêmes (Phase 38 de la mission).

## Vulnerability Summary

| ID | Severity | Vulnerability | Component | Status |
| --- | --- | --- | --- | --- |
| SEC-001 | High | Race condition (TOCTOU) contournant l'invariant « un rejet bloque définitivement » | `learning.py`, `alerts.py` | **FIXED, VERIFIED** |
| SEC-002 | Medium | Absence totale de CSP/HSTS/Permissions-Policy | `http.py`, `scripts/dev_server.py` | **FIXED, VERIFIED** |
| SEC-003 | Low | Incohérence de rate limiting (PHQ-9 non protégé) | `http.py` | **FIXED, VERIFIED** |
| INFO-001 | Informational | Pas de gestion `X-Forwarded-For` pour le rate limiting par IP derrière un reverse proxy | `http.py` | Documenté, non corrigé (voir justification) |
| INFO-002 | Informational | Fenêtre de course résiduelle bénigne sur double-approbation simultanée exacte | `learning.py` | Documenté, accepté (fail-safe) |

---

### SEC-001

**Title:** Race condition (TOCTOU) sur les transitions d'état métier critiques

**Severity:** High

**CVSS (estimation qualitative):** 7.1 (AV:N/AC:H/PR:L/UI:N/S:U/C:N/I:H/A:N) — nécessite un timing précis (deux requêtes authentifiées concurrentes), mais l'impact sur l'intégrité d'une décision de sécurité clinique est élevé.

**CWE:** CWE-362 (Concurrent Execution using Shared Resource with Improper Synchronization, 'Race Condition') / CWE-367 (TOCTOU)

**Location:** `backend/app/learning.py::decide_model_version` (lignes ~187-195 avant correction), `backend/app/learning.py::review_feedback` (lignes ~86-92), `backend/app/alerts.py::transition` (lignes ~16-19)

**Affected component:** Registre de modèles IA (approbation clinique), file de revue de l'apprentissage continu, machine à états des alertes de crise.

**Description:** Chacune des trois fonctions lisait un statut (`SELECT`), le validait en Python, puis écrivait (`UPDATE`) sans qu'aucune contrainte ne garantisse que le statut n'avait pas changé entre les deux opérations. Deux requêtes concurrentes pouvaient toutes deux lire le même état de départ valide, puis toutes deux écrire — la seconde écriture écrasant silencieusement la première.

**Root cause:** Absence de verrouillage optimiste (compare-and-swap) sur les colonnes de statut ; `UPDATE ... WHERE id=?` sans condition sur l'état lu.

**Attack scenario:** Un modèle de risque IA a déjà une approbation. Clinicien A l'examine et le **rejette** (biais détecté). Concurremment, Clinicien B, dont la requête avait déjà lu l'état « en attente » avant le rejet de A, soumet une **approbation** qui atteint le seuil de deux approbations. Sans le correctif, l'écriture de B s'exécute après celle de A et écrase silencieusement `REJECTED` par `APPROVED` — un modèle explicitement rejeté par un clinicien devient déployable.

**Impact:** Contournement d'un contrôle de sécurité clinique explicitement exigé par la conception du projet (Section 15 : « validation par deux psychologues », rejet unique bloquant). Dans le cas de l'alerte, une alerte de crise annulée par un clinicien pourrait silencieusement redevenir « escaladée » selon un tiers non informé, ou l'inverse — un risque direct pour la fiabilité du processus de sécurité patient.

**Evidence:** Reproduit de manière déterministe avec deux connexions SQLite séparées (simulant deux requêtes concurrentes réelles), sans dépendre du hasard du threading — voir la commande d'audit exécutée et son résultat (`FINAL STATUS: APPROVED` avant correctif, alors que A avait rejeté). Test de régression permanent : `tests/test_security.py::BusinessLogicRaceConditionTests` (3 tests, un par fonction corrigée).

**Recommended remediation:** Garder l'`UPDATE` avec une clause `WHERE ... AND status = <état lu>`, vérifier `cursor.rowcount`, et lever une erreur explicite en cas de conflit plutôt que d'écraser silencieusement. *(Appliqué.)*

**Priority:** Immédiate (avant tout usage du registre de modèles ou du moteur d'alerte en conditions réelles).

**Fix status:** **FIXED, REGRESSION TEST ADDED, RE-TESTED, VERIFIED.**

---

### SEC-002

**Title:** Absence de Content-Security-Policy, Strict-Transport-Security et Permissions-Policy

**Severity:** Medium

**CVSS (estimation qualitative):** 5.4 (AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N) — défense en profondeur manquante, pas une vulnérabilité directement exploitable seule (aucune XSS trouvée par ailleurs, voir Phase 10), mais un facteur aggravant en cas de découverte future d'une XSS, et un manquement direct à la Section 16 du prompt maître du projet lui-même.

**CWE:** CWE-1021 (Improper Restriction of Rendered UI Layers, lié à l'absence de `frame-ancestors`), CWE-693 (Protection Mechanism Failure)

**Location:** `backend/app/http.py` (liste `headers`), `scripts/dev_server.py::_serve_static`

**Affected component:** Toutes les réponses de l'API et des trois frontends statiques.

**Description:** Seuls `X-Content-Type-Options`, `X-Frame-Options` et `Referrer-Policy` étaient présents. Aucune CSP, aucun HSTS, aucune Permissions-Policy.

**Root cause:** Non implémenté lors des phases précédentes ; jamais audité spécifiquement avant cette mission.

**Attack scenario:** En l'absence de CSP, une XSS future (même mineure) aurait un impact maximal (exécution de script arbitraire sans restriction de source). En l'absence de HSTS, une future mise en production sur TLS resterait vulnérable au downgrade HTTP lors de la première visite.

**Impact:** Facteur aggravant potentiel, pas une brèche en soi (aucune XSS active trouvée — voir Phase 10 de l'historique du projet et l'audit manuel refait dans cette mission).

**Evidence:** Vérifié par lecture directe du code avant correctif (absence confirmée), puis par test automatisé après correctif (`tests/test_security.py::SecurityHeadersTests`), et par vérification en navigateur réel que la CSP stricte n'empêche aucune fonctionnalité existante (aucune violation, `fetch()` réel testé avec succès, script/style déjà 100 % auto-hébergés sans handler inline).

**Recommended remediation:** `default-src 'none'` sur l'API (JSON pur, rien à rendre) ; `default-src 'self'; script-src 'self'; style-src 'self'` sur les frontends statiques ; HSTS `max-age=63072000; includeSubDomains` ; Permissions-Policy désactivant les fonctions navigateur non utilisées. *(Appliqué.)*

**Priority:** Élevée (défense en profondeur, coût de correction minimal, aucune régression possible étant donné l'absence de script inline).

**Fix status:** **FIXED, REGRESSION TEST ADDED, RE-TESTED, VERIFIED (y compris vérification navigateur réelle).**

---

### SEC-003

**Title:** Incohérence de rate limiting — endpoint PHQ-9 non protégé

**Severity:** Low

**CVSS (estimation qualitative):** 3.1 (AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L)

**CWE:** CWE-770 (Allocation of Resources Without Limits or Throttling)

**Location:** `backend/app/http.py`, route `POST /api/v1/assessments/phq9`

**Description:** L'endpoint d'envoi de message était protégé par un rate limit (30/minute/patient) depuis la Phase 10, mais l'endpoint de soumission PHQ-9 — un endpoint d'écriture patient équivalent en sensibilité — n'avait aucune limite.

**Root cause:** Oubli lors de l'ajout du rate limiting en Phase 10 (le message-sending a été identifié comme prioritaire, PHQ-9 ne l'a pas été à l'époque).

**Impact:** Un patient (ou un compte compromis) pouvait polluer indéfiniment son propre historique PHQ-9, dégradant la lisibilité clinique de son suivi pour son clinicien — un impact sur l'intégrité des données cliniques, pas une fuite ou un contournement d'autorisation.

**Evidence:** Confirmé par lecture du routeur (aucun appel à un limiteur avant `service.submit_phq9`) ; corrigé et vérifié par `tests/test_security.py::RateLimitingTests::test_phq9_submission_flooding_by_one_patient_is_throttled`.

**Recommended remediation:** Réutiliser le `RateLimiter` générique déjà en place, 20/heure/patient. *(Appliqué.)*

**Priority:** Basse mais triviale à corriger — traitée dans la même session.

**Fix status:** **FIXED, REGRESSION TEST ADDED, RE-TESTED, VERIFIED.**

---

### INFO-001

**Title:** Rate limiting par IP non fiable derrière un reverse proxy non configuré

**Severity:** Informational

**Location:** `backend/app/http.py`, usage de `environ.get("REMOTE_ADDR", "")`

**Description:** Si ce service est un jour déployé derrière un reverse proxy (nginx, load balancer cloud) sans configuration explicite, `REMOTE_ADDR` refléterait l'IP du proxy pour tous les clients, faisant que le rate limit d'inscription (10/heure) s'appliquerait globalement à tous les utilisateurs réels combinés, pas par client.

**Why not fixed now:** Faire confiance à l'en-tête `X--Forwarded-For` sans connaître la chaîne de proxys de confiance serait **une nouvelle vulnérabilité** (un attaquant pourrait usurper son IP apparente en falsifiant cet en-tête directement, contournant tout rate limiting). Corriger cela correctement nécessite de connaître l'architecture de déploiement réelle (nombre de proxys de confiance, lesquels), qui n'existe pas encore pour ce projet.

**Risk:** Faible tant qu'aucune infrastructure de production n'existe. Deviendra pertinent au moment du déploiement réel.

**Recommended remediation:** Au moment du déploiement, configurer le nombre exact de proxys de confiance et n'utiliser que l'en-tête `X-Forwarded-For` correspondant à une position fixe et vérifiée dans la chaîne (jamais la valeur brute fournie par le client).

**Manual action required:** Décision d'architecture de déploiement, à prendre avec l'équipe infrastructure au moment venu — pas une action de code aujourd'hui.

---

### INFO-002

**Title:** Fenêtre de course résiduelle bénigne sur double-approbation simultanée exacte

**Severity:** Informational

**Location:** `backend/app/learning.py::decide_model_version`

**Description:** Trouvé lors du second passage adversarial contre le correctif SEC-001 lui-même (Phase 38 de la mission). Si **deux approbations légitimes** (pas un rejet contre une approbation, mais deux approbations) atteignent le seuil de 2 exactement au même instant, l'une des deux écritures de statut peut échouer avec l'erreur « déjà décidé concurremment », alors qu'il s'agit en réalité d'un résultat parfaitement légitime (le modèle finit bien `APPROVED`).

**Why not fixed further:** Le vote du clinicien « perdant » cette course est **correctement enregistré** dans `model_approvals` (l'audit est complet et exact) ; seul le message de statut retourné à cette requête particulière est trompeur (« conflit » alors que le résultat final est correct). Corriger ce cas précisément demanderait de distinguer « conflit réel » (un rejet a eu lieu) de « double approbation bénigne au même seuil » — une complexité supplémentaire pour un cas à très faible probabilité (deux clics à la milliseconde près) dont le pire effet est un message d'erreur déroutant, jamais un état de données incorrect. Le comportement fail-safe (ne jamais écraser silencieusement) est préservé.

**Risk:** Négligeable — aucun impact sur l'intégrité des données, seulement sur la clarté d'un message d'erreur dans un cas extrêmement rare.

**Recommended remediation (future, non prioritaire):** Si ce cas devient gênant en pratique, distinguer explicitement dans le message d'erreur « le statut a changé vers REJECTED » (vrai conflit) de « le statut a déjà été mis à APPROVED par une autre approbation concurrente » (résultat bénin) en relisant le statut final avant de lever l'exception.

## Résultat par vulnérabilité (traçabilité complète)

- **SEC-001** : FOUND → ANALYZED → FIXED → REGRESSION TEST ADDED (3 tests) → RE-TESTED → VERIFIED
- **SEC-002** : FOUND → ANALYZED → FIXED → REGRESSION TEST ADDED (2 tests) → RE-TESTED → VERIFIED (+ vérification navigateur réelle)
- **SEC-003** : FOUND → ANALYZED → FIXED → REGRESSION TEST ADDED (1 test) → RE-TESTED → VERIFIED
- **INFO-001** : FOUND → ANALYZED → documenté, action manuelle requise au déploiement
- **INFO-002** : FOUND (lors du second passage contre SEC-001) → ANALYZED → accepté comme compromis raisonnable, documenté
