# PHASE REPORT

Phase: 13 — Parcours de bout en bout (E2E)
Date: 2026-08-27
Objectif: Exécuter, sous forme automatisée et rejouable, les quatre parcours nommés par la Section 43 du prompt maître : utilisateur normal, détresse, crise, apprentissage — chacun comme une histoire complète, pas comme des vérifications isolées par domaine.

## 0. Cadrage : E2E applicatif, pas E2E navigateur

Chaque module impliqué dans ces parcours a déjà été vérifié manuellement dans un vrai navigateur au moment de sa construction (Phases 7, 8a, 8b, 23 — voir les rapports correspondants). Ce que ces vérifications manuelles ne donnent pas, c'est une garantie **rejouable et automatisée** que l'intégration entre les modules continue de fonctionner après un futur changement. `tests/test_e2e_journeys.py` comble ce manque au niveau applicatif : chaque test appelle la vraie application WSGI (`application(settings)`) exactement comme le ferait un client HTTP, de bout en bout, à travers tous les domaines que le parcours traverse.

Ceci n'est délibérément pas un E2E piloté par navigateur (Playwright ou équivalent) : ajouter une telle dépendance est une décision que l'utilisateur doit prendre explicitement, pas quelque chose à introduire unilatéralement pour cocher une case. La distinction est documentée en tête du fichier de test lui-même, pas seulement ici.

## 1. Travaux réalisés

- `tests/test_e2e_journeys.py`, quatre parcours complets :
  - **Utilisateur normal** : inscription → consentement → profil (onboarding) → conversation (message calme, accusé de réception normal) → PHQ-9 (score vérifié) → un administrateur assigne un clinicien → le clinicien voit le patient dans son tableau de bord avec le bon score PHQ-9 et zéro alerte ouverte, et une timeline cohérente.
  - **Détresse (ORANGE)** : message ambigu → alerte ORANGE ouverte, scopée au bon clinicien → une notification a été tentée et enregistrée (honnêtement `SKIPPED_NO_CHANNEL` par défaut, mais la tentative existe) → le clinicien prend en compte l'alerte.
  - **Crise (ROUGE)** : message à haut risque → réponse de sécurité fixe (jamais le répondeur) → alerte ROUGE → parcours complet de la machine à états (ESCALATED → RESOLVED) avec justification obligatoire à chaque étape, et vérification que chaque transition a laissé une trace d'audit (`alert_actions`).
  - **Apprentissage** : message d'un patient consentant → échantillonnage → anonymisation → revue par un premier clinicien → dataset finalisé → enregistrement d'un modèle → double approbation par deux clinicien·ne·s réellement distinct·e·s → déploiement → **rollback** (la Section 15 exige explicitement cette capacité ; ce parcours la vérifie jusqu'au bout, pas seulement le déploiement).

## 2. Fichiers créés

- `tests/test_e2e_journeys.py`
- `docs/reports/phase-13-e2e-journeys.md`

## 3. Fichiers modifiés

- `scripts/benchmark.py` : corrections mineures trouvées en re-passant les outils de durcissement pendant cette phase (voir Section 8) — sans lien direct avec les parcours E2E eux-mêmes, mais découvertes en vérifiant que rien n'avait régressé.

## 4. Architecture impactée

Aucune. Cette phase ajoute une suite de tests d'intégration de bout en bout ; elle ne modifie aucun contrat d'API ni schéma de données applicatif.

## 5. Fonctionnalités terminées

- Les quatre parcours nommés par le prompt maître sont désormais vérifiés automatiquement, de façon rejouable, à chaque exécution de la suite de tests — pas seulement lors d'une vérification manuelle ponctuelle.

## 6. Tests exécutés

- `python -m unittest discover -s tests -v`
- `ruff check backend tests scripts ml`, `mypy backend`, `bandit -r backend scripts -q`, `pip-audit`, `python scripts/scan_secrets.py`
- `coverage run` + `coverage report`

## 7. Résultats des tests

- 87 tests automatisés, tous verts (4 nouveaux parcours E2E). Aucune régression.
- Couverture : 92 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- Aucun signalement `ruff`, `mypy`, `bandit`, `pip-audit`, scanner de secrets après corrections (Section 8).

## 8. Bugs détectés

- Trois variables locales inutilisées (`admin_id`) dans le nouveau fichier de test, trouvées par `ruff` (F841) — style, pas fonctionnel.
- En repassant `bandit` sur l'ensemble du projet pendant cette phase, deux signalements réels sur `scripts/benchmark.py` (écrit en Phase 11–12) sont apparus : un mot de passe de test codé en dur (faux positif, même motif que les autres tests) et l'usage d'`assert` pour valider les réponses HTTP dans un script — `assert` est supprimé silencieusement si le script est exécuté avec `python -O`, ce qui transformerait un échec réel en un simple trou dans les mesures plutôt qu'une erreur visible.

## 9. Bugs corrigés

- Nettoyage des variables inutiles (Section 8).
- `scripts/benchmark.py` : les six `assert status == "201 Created"` sont remplacés par une fonction `_expect_created()` qui lève une exception explicite, robuste à l'optimisation Python. Le mot de passe de test est marqué `# nosec B105` avec justification, cohérent avec les suppressions déjà en place ailleurs dans le projet.

## 10. Vulnérabilités détectées

Aucune. Les deux signalements de la Section 8 concernent un script de bench interne, pas une surface exposée à un utilisateur.

## 11. Vulnérabilités corrigées

Sans objet au-delà de la Section 9.

## 12. Dette technique

- Pas de suite E2E pilotée par un vrai navigateur (Playwright ou équivalent) : chaque parcours a été vérifié manuellement dans un navigateur réel au moment de sa construction, mais cette vérification n'est pas rejouable automatiquement. Ajouter cet outillage est une décision de dépendance à prendre avec l'utilisateur, pas unilatéralement.
- Les parcours E2E utilisent des comptes clinicien/admin provisionnés directement via `AuthService` (comme le ferait un opérateur avec `scripts/provision_user.py`), pas via une future interface d'auto-inscription qui n'existe pas et ne doit pas exister pour ces rôles (voir Phase 7).

## 13. Décisions techniques

- E2E au niveau HTTP/applicatif plutôt qu'au niveau navigateur : capture la même classe de régression (rupture d'intégration entre modules) sans ajouter de dépendance lourde, et reste rapide à exécuter en CI (les 4 parcours s'exécutent en environ 1,5 seconde).
- Chaque parcours est un test unique et long plutôt que découpé en petites étapes séparées : c'est délibéré, cela reflète directement la structure narrative demandée par la Section 43 du prompt maître (« Registration → Consent → Onboarding → Chat → PHQ-9 → Dashboard », etc.), et rend la correspondance entre le test et l'exigence immédiatement lisible.

## 14. Risques restants

- Sans E2E navigateur automatisé, une régression purement côté frontend (JavaScript cassé, mauvais endpoint appelé) pourrait passer inaperçue entre deux vérifications manuelles. Le risque est mitigé mais pas éliminé par la vérification manuelle déjà faite phase par phase.

## 15. Métriques

- 4 parcours E2E complets, 87 tests au total (contre 83 avant cette phase).
- 2 corrections de durcissement supplémentaires trouvées en repassant les outils existants sur du code d'une phase précédente.
- Temps d'exécution des 4 parcours E2E : environ 1,5 seconde.

## 16. Critères de sortie

- [x] Parcours utilisateur normal automatisé et vérifié.
- [x] Parcours détresse (ORANGE) automatisé et vérifié.
- [x] Parcours crise (ROUGE), y compris escalade et résolution, automatisé et vérifié.
- [x] Parcours apprentissage, y compris double approbation et rollback, automatisé et vérifié.
- [ ] E2E piloté par un vrai navigateur — hors de portée sans décision explicite d'ajouter une dépendance d'automatisation de navigateur.

## 17. Conclusion

Les quatre parcours que le prompt maître demande de vérifier existent maintenant comme des tests automatisés et rejouables, pas seulement comme des vérifications manuelles ponctuelles dispersées dans les rapports de phase précédents. Cette phase a aussi montré la valeur de repasser systématiquement les outils de durcissement sur l'ensemble du projet, pas seulement sur le code nouvellement écrit : deux corrections réelles sur un script de la phase précédente ont été trouvées de cette façon.

STATUS: PASS
