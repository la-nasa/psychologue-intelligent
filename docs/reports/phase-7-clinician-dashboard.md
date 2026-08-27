# PHASE REPORT

Phase: 7 — Clinician Dashboard (patients, relationships, alerts, timeline)
Date: 2026-08-26
Objectif: Relations patient-clinicien scopées côté serveur, RBAC renforcé, et un tableau de bord clinicien qui expose enfin en toute sécurité le pipeline de crise construit en Phase 5–6.

## 1. Travaux réalisés

- MFA obligatoire étendue au rôle `ADMIN` (elle ne couvrait que `CLINICIAN`) : toute action sensible d'administration exige désormais un second facteur.
- `AuthService.provision_privileged_user` : les comptes clinicien/admin ne sont jamais auto-inscrits sur HTTP ; ils sont provisionnés hors bande par un opérateur (`scripts/provision_user.py`), qui génère un secret TOTP et ne l'affiche qu'une fois.
- Migration `006_patient_clinician_relationships` : relation patient-clinicien avec statut, `created_by`, horodatages, et un index unique partiel garantissant au plus une relation `ACTIVE` par paire patient/clinicien (l'historique des relations terminées est conservé).
- Nouveau module `backend/app/clinician.py` : création/fin de relation (réservée à `ADMIN`), vérification d'appartenance (`require_active_relationship`) systématique avant toute lecture ou action sur un patient, liste des patients d'un clinicien, timeline complète (profil, historique PHQ-9, alertes, actions), liste d'alertes scopée avec filtres niveau/statut, et action sur alerte réutilisant la machine à états de la Phase 5–6.
- Nouvelles routes HTTP (toutes exigent un rôle et, pour les routes clinicien, une relation active vérifiée côté serveur — jamais côté client) : `POST /api/v1/admin/relationships`, `POST /api/v1/admin/relationships/{id}/end`, `GET /api/v1/clinician/patients`, `GET /api/v1/clinician/patients/{id}/timeline`, `GET /api/v1/clinician/alerts`, `POST /api/v1/clinician/alerts/{id}/actions`.
- Correction d'un bug de fondation découvert en écrivant les tests : toute requête `POST` avec un corps vide (ex. `end relationship`, qui n'a pas de champ obligatoire) était rejetée à tort en `413 Payload Too Large` parce que le contrôle de taille interdisait une longueur de 0. Un corps vide est désormais traité comme `{}`.
- Frontend clinicien complet (`frontend/clinician/`) : connexion avec TOTP, liste de patients scopée, timeline (PHQ-9 + alertes), vue transverse des alertes avec filtres, formulaire d'action avec justification obligatoire et options limitées aux transitions valides pour le statut courant.
- `scripts/dev_server.py` : serveur de développement qui sert les deux frontends et l'API sur une seule origine (aucun proxy CORS nécessaire), explicitement documenté comme non destiné à la production.
- Vérification fonctionnelle réelle dans un navigateur (pas seulement des tests automatisés) : connexion clinicien avec code TOTP généré dynamiquement, visualisation d'un patient avec une alerte ROUGE, prise en compte de l'alerte avec justification, et vue transverse des alertes — voir Section 6.

## 2. Fichiers créés

- `backend/app/clinician.py`
- `scripts/provision_user.py`, `scripts/dev_server.py`
- `frontend/clinician/index.html`, `frontend/clinician/app.js`, `frontend/clinician/styles.css`
- `.claude/launch.json` (configuration de prévisualisation locale, outillage de développement)
- `tests/test_clinician_dashboard.py`
- `docs/reports/phase-7-clinician-dashboard.md`

## 3. Fichiers modifiés

- `backend/app/auth.py` (MFA pour `ADMIN`, `provision_privileged_user`)
- `backend/app/db.py` (migration `006`)
- `backend/app/http.py` (nouvelles routes, correction du bug de corps vide, routeur à motifs de chemin)

## 4. Architecture impactée

Le domaine Clinician Dashboard existe maintenant et s'appuie sur le domaine Alert/Crisis de la Phase 5–6 sans dupliquer sa logique : `clinician.act_on_alert` délègue à `alerts.transition`. Aucune route ne fait confiance à un identifiant fourni par le client sans vérifier une relation active en base ; c'est la mitigation concrète de TH-02 (BOLA) du threat model, pas seulement une déclaration d'intention.

## 5. Fonctionnalités terminées

- Provisioning hors bande de comptes clinicien/admin avec MFA obligatoire.
- Relations patient-clinicien créées/terminées par un administrateur, avec unicité de la relation active.
- Dashboard clinicien : liste de patients, timeline complète, alertes filtrables, actions avec justification — tout scopé par relation active, vérifié côté serveur à chaque appel.
- Interface fonctionnelle vérifiée dans un navigateur réel, pas seulement en test automatisé.

## 6. Tests exécutés

- `python -m compileall -q backend tests scripts`
- `python -m unittest discover -s tests -v`
- Vérification manuelle dans le navigateur (voir capture de session) : connexion clinicien avec TOTP réel, affichage d'une patiente avec score PHQ-9 et alerte ROUGE, prise en compte de l'alerte (transition OPEN → ACKNOWLEDGED confirmée dans l'UI et dans les options d'action suivantes), vue transverse des alertes.
- Scan de recherche de secrets codés en dur sur `backend/`, `frontend/`, `scripts/`, `config/`.

## 7. Résultats des tests

- 29 tests automatisés, tous verts (8 nouveaux pour cette phase). Aucune régression sur les 21 tests précédents.
- Tests IDOR/BOLA négatifs explicites : un clinicien sans relation active ne voit aucun patient, aucune alerte de ce patient, et ne peut pas agir sur une de ses alertes (401, pas de fuite d'information sur l'existence de la ressource).
- Vérification navigateur : succès pour la connexion MFA, l'affichage scopé, l'action sur alerte et le rafraîchissement des transitions disponibles.
- Aucune erreur console JavaScript observée pendant la session de vérification.
- Aucun secret codé en dur détecté.

## 8. Bugs détectés

- Le bug des requêtes `POST` à corps vide rejetées en `413` (voir Section 1), découvert par le test `test_ending_a_relationship_revokes_access` avant toute exécution manuelle.

## 9. Bugs corrigés

- Correction ci-dessus, revérifiée par l'ensemble de la suite (aucune régression sur les routes existantes qui envoient toujours un corps non vide).

## 10. Vulnérabilités détectées

| ID | Menace | Impact | Probabilité | Risque | Mitigation | Test |
| --- | --- | --- | --- | --- | --- | --- |
| TM-10 | `scripts/dev_server.py` mal utilisé en production | Servir des fichiers statiques sans TLS, cache ni durcissement | Faible si la documentation est respectée | Moyen | Docstring explicite « ne jamais utiliser comme serveur de production » ; à exclure de tout déploiement réel | Revue de configuration de déploiement (Phase 10) |

## 11. Vulnérabilités corrigées

- L'absence de séparation de rôle MFA entre `CLINICIAN` et `ADMIN` (un administrateur pouvait se connecter sans second facteur) est corrigée : les deux rôles l'exigent désormais.

## 12. Dette technique

- Pas d'interface d'administration pour créer les relations patient-clinicien : l'endpoint existe et est testé, mais doit être appelé directement (`curl`/script) tant que la console d'administration (Section 23 du prompt maître) n'est pas construite. C'est un choix délibéré pour ne pas construire une UI d'administration à moitié pensée avant la Phase dédiée.
- Le tableau de bord clinicien ne propose pas encore d'annotation clinique, de correction de réponse IA, ni de reporting (Section 37) : ce sont des fonctionnalités de la Phase 8 (Learning System / human feedback), pas de la Phase 7.
- `scripts/dev_server.py` n'a ni cache, ni compression, ni TLS : strictement un outil de développement local, documenté comme tel.
- Le dashboard n'affiche pas encore de tendance visuelle du PHQ-9 (uniquement un tableau) : suffisant pour une revue clinique ponctuelle, mais un graphique serait plus lisible pour un suivi longitudinal ; reporté pour ne pas ajouter de dépendance de rendu graphique sans besoin validé.

## 13. Décisions techniques

- Pas de tables `clinicians`/`patients` séparées comme le suggérait le modèle de données de la Phase 1 : `patient_clinician_relationships` référence directement `users.id`, cohérent avec le choix déjà fait pour `profiles` en Phase 3. La séparation pseudonymisée pour l'analytique est réintroduite quand un consommateur d'analytique existera réellement (Phase Analytics), pas par anticipation.
- Les erreurs d'autorisation (rôle incorrect ou relation absente) renvoient `401` comme les erreurs de session invalide, pour rester cohérent avec la convention déjà établie en Phase 2 plutôt que d'introduire `403` de façon incohérente à mi-chemin du projet.
- Assignation des relations réservée à `ADMIN` plutôt qu'un flux de consentement patient-clinicien en libre-service, non spécifié par le document source et risqué à improviser sans validation clinique.

## 14. Risques restants

- Sans console d'administration, la création de relations en conditions réelles dépend d'un opérateur de confiance exécutant des appels API directs : acceptable en pilote restreint, pas à plus grande échelle.
- Le dashboard n'a pas encore été vu par un clinicien réel : l'ergonomie et la terminologie doivent être validées avant tout usage clinique, conformément à la Section 52 du prompt maître.

## 15. Métriques

- 1 migration ajoutée (006), 1 nouvelle table, 1 index unique partiel.
- 6 nouvelles routes HTTP, toutes couvertes par au moins un test positif et un test négatif d'autorisation.
- 8 nouveaux tests (29 au total), 0 nouvelle dépendance externe.
- 2 nouveaux frontends statiques (patient existant + clinicien), servis en local sur une seule origine par un outil de développement dédié.

## 16. Critères de sortie

- [x] Relations patient-clinicien avec RBAC et vérification d'appartenance côté serveur.
- [x] Dashboard clinicien : patients, timeline, alertes, actions.
- [x] Recherche/filtrage des alertes par niveau et statut.
- [x] Vérifié fonctionnellement dans un navigateur réel, pas seulement en test automatisé.
- [ ] Annotation clinique / feedback IA (Phase 8).
- [ ] Console d'administration pour la gestion des relations (reportée).

## 17. Conclusion

Le pipeline de crise de la Phase 5–6 est maintenant exposé de façon sûre : chaque lecture et chaque action clinicien passe par une vérification de relation active côté serveur, jamais par un identifiant de confiance envoyé par le client. Le dashboard a été vérifié manuellement dans un navigateur, pas seulement testé automatiquement. La dette assumée (pas de console d'administration, pas encore d'annotation clinique) est documentée. Le prochain gate naturel est la Phase 8 : apprentissage continu contrôlé, anonymisation, feedback humain et registre de modèles — ou, si la priorité clinique l'exige davantage, une itération de durcissement (Phase 10) avant d'aller plus loin fonctionnellement.

STATUS: PASS WITH WARNINGS
