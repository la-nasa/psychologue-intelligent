# PHASE REPORT

Phase: 10 (suite) — Durcissement sécurité : tests adversariaux, audit XSS frontend, rate limiting étendu, mise à jour du threat model
Date: 2026-08-27
Objectif: Après le premier passage de durcissement CI (lint/type-check/SAST/audit de dépendances/scan de secrets, voir `phase-10-ci-hardening.md`), exécuter la suite de tests de sécurité proprement dite exigée par la Section 17 (Niveau 5) du prompt maître : injection, contournement d'authentification, traversée de chemin, élévation de privilèges, rate limiting, abus de charge utile — puis mettre le threat model à jour pour qu'il reflète l'état réel du système plutôt que sa conception de Phase 1.

## 1. Travaux réalisés

- **Audit XSS manuel des trois frontends** : chaque usage de `innerHTML` a été examiné individuellement. Résultat : tout contenu réellement contrôlé par un utilisateur (e-mail, nom affiché, contenu de message, contenu anonymisé, version/métriques de modèle) passe déjà par `escapeHtml()` ou `textContent`. Aucune faille trouvée, mais c'est la première fois que cette vérification est faite systématiquement plutôt que par habitude au moment de l'écriture du code.
- `tests/test_security.py` : nouvelle suite dédiée, distincte des tests négatifs déjà présents dans chaque domaine, couvrant les classes d'attaque transverses :
  - Traversée de chemin contre `scripts/dev_server.py` (payloads `../`, chemins absolus).
  - Injection SQL contre le login (n'a jamais fonctionné, comme attendu avec des requêtes paramétrées partout) et confirmation qu'un `DROP TABLE` tenté via un champ e-mail ne détruit rien.
  - Payload `<script>` dans un message : stocké et relu tel quel, jamais interprété côté serveur.
  - Contournement d'authentification : en-tête manquant, schéma malformé, jeton trafiqué, jeton révoqué.
  - Absence de cookie sur `/auth/sessions` (confirme que le CSRF classique ne s'applique pas à cette architecture par jeton `Bearer`).
  - Élévation de privilèges : un champ `role` injecté dans une mise à jour de profil est ignoré ; un patient ne peut atteindre aucune route admin/clinicien.
  - Abus de charge utile : corps surdimensionné, mauvais `Content-Type`, JSON malformé, route inconnue — aucun de ces cas ne renvoie de trace ni de 500.
  - Fuite de secret : `/me` ne renvoie jamais `password_hash`/`mfa_secret`/`token_hash` ; une tentative de connexion échouée ne permet pas de distinguer un compte existant d'un compte inexistant (comparaison des corps de réponse hors `trace_id`, qui est un identifiant de corrélation légitimement aléatoire).
- **Deux vrais bugs de test trouvés en exécutant cette suite pour la première fois** (Section 8) — corrigés, pas de vulnérabilité réelle derrière.
- **Rate limiting étendu** : la classe `LoginLimiter` a été généralisée en `RateLimiter` et appliquée non seulement au login, mais aussi à l'inscription (10/heure par IP) et à l'envoi de message (30/minute par patient) — jusqu'ici seul le login était protégé.
- **Mise à jour complète du threat model** (`docs/security/threat-model.md`) : chaque menace porte désormais un statut de vérification (« Vérifié » avec référence de test, « Partiellement vérifié », ou « Non résolu »), une correction d'une inexactitude (le document affirmait Argon2id ; l'implémentation utilise PBKDF2-HMAC-SHA256, écart déjà assumé depuis l'ADR-003 mais jamais reporté ici), et l'ajout des menaces découvertes en cours de route (traversée de chemin, absence de CSRF par construction).

## 2. Fichiers créés

- `tests/test_security.py`
- `docs/reports/phase-10-security-hardening.md`

## 3. Fichiers modifiés

- `backend/app/http.py` (`LoginLimiter` → `RateLimiter`, rate limiting sur l'inscription et l'envoi de message)
- `docs/security/threat-model.md` (réécriture complète avec statuts de vérification)

## 4. Architecture impactée

Aucune. Cette phase ajoute des tests et des limites de débit ; elle ne change aucun contrat d'API ni schéma de données.

## 5. Fonctionnalités terminées

- Suite de tests de sécurité transverse, distincte des tests métier, exécutée en CI au même titre que le reste.
- Rate limiting sur les trois points d'entrée les plus exposés à l'abus (login, inscription, envoi de message).
- Threat model synchronisé avec l'état réel du code, avec traçabilité vers les tests qui vérifient chaque affirmation.

## 6. Tests exécutés

- `python -m unittest discover -s tests -v`
- `ruff check backend tests scripts ml`, `mypy backend`, `bandit -r backend scripts -q`, `pip-audit`, `python scripts/scan_secrets.py`
- `coverage run` + `coverage report`

## 7. Résultats des tests

- 79 tests automatisés, tous verts (23 nouveaux dans `test_security.py`, dont 2 pour le rate limiting étendu). Aucune régression.
- Couverture : 92 % sur `backend/app`, au-dessus du seuil CI de 85 %.
- Aucun signalement `ruff`, `mypy`, `bandit`, `pip-audit`, scanner de secrets.
- Audit XSS manuel : 0 faille trouvée sur les usages `innerHTML` des trois frontends.

## 8. Bugs détectés

Deux bugs dans les tests eux-mêmes, révélant au passage un comportement du système qui n'était pas documenté avant :
1. `test_unknown_route_returns_404` attendait un `404` pour une route inconnue appelée sans authentification, et obtenait `401`. En creusant : le contrôle d'authentification s'exécute avant la résolution de route pour tout endpoint non explicitement exempté (santé, inscription, connexion) — un appelant non authentifié ne peut donc même pas savoir si une route existe. C'est un comportement voulu et plus sûr (pas d'énumération de routes sans authentification), pas un bug applicatif ; seul le test avait la mauvaise attente.
2. `test_failed_login_error_does_not_reveal_whether_the_account_exists` comparait les corps de réponse octet pour octet, sans exclure `trace_id` — un identifiant de corrélation aléatoire par requête, qui diffère légitimement à chaque appel. Le test échouait à cause de sa propre trop grande exigence, pas à cause d'une fuite réelle.

## 9. Bugs corrigés

- Les deux tests ci-dessus ont été corrigés pour vérifier le comportement réellement voulu (voir Section 8) plutôt que d'affaiblir la vérification.
- Aucun bug de code applicatif trouvé par cette suite — c'est un résultat positif, pas une lacune de la suite : chaque classe d'attaque a été testée avec un payload réel, pas seulement supposée bloquée.

## 10. Vulnérabilités détectées

Aucune vulnérabilité exploitable trouvée. Deux limites déjà connues sont réaffirmées avec un statut clair dans le threat model plutôt que silencieusement oubliées :
- Le rate limiter reste en mémoire de processus (TH-10) : suffisant pour une instance unique de développement, à remplacer avant un déploiement multi-instance.
- Le risque prompt injection (TH-04) est actuellement sans objet puisqu'aucun LLM génératif n'est intégré ; il redeviendra pleinement pertinent le jour où ce choix changera, et devra être ré-audité à ce moment-là, pas avant.

## 11. Vulnérabilités corrigées

- Sans objet : aucune vulnérabilité réelle n'a été trouvée cette phase (voir Section 10). Le travail a consisté à vérifier des affirmations déjà faites, pas à corriger des failles.

## 12. Dette technique

- Rate limiter en mémoire, non partagé entre instances (déjà noté).
- Pas de scan automatisé des logs applicatifs en conditions réelles (seulement du code source).
- Pas de test de charge/spike réel (Phase 11 du prompt maître, non commencée).
- Pas de corpus de tests adversariaux IA (jailbreak/injection) — sans objet tant qu'aucun LLM génératif n'est intégré, mais à constituer avant cette intégration, pas après.

## 13. Décisions techniques

- Suite de sécurité séparée des tests de domaine plutôt que dispersée : les tests d'autorisation négative restent dans leur fichier de domaine (ils vérifient une règle métier précise), tandis que `test_security.py` regroupe les classes d'attaque transverses qui ne appartiennent à aucun domaine en particulier — plus facile à faire évoluer comme un corpus de sécurité à part entière.
- `RateLimiter` généralisé plutôt qu'une nouvelle classe par cas d'usage : même primitive (fenêtre glissante en mémoire), juste des paramètres et des clés différents.

## 14. Risques restants

- Le threat model reste un document vivant : toute nouvelle frontière de confiance (ex. intégration d'un LLM réel, ajout d'un canal de notification réel) doit le mettre à jour avant, pas après, conformément à la pratique déjà établie sur ce projet.
- Aucune de ces vérifications ne remplace un test d'intrusion réel par une équipe de sécurité externe avant un pilote clinique.

## 15. Métriques

- 23 nouveaux tests de sécurité dédiés (79 au total), 2 bugs de test trouvés et corrigés, 0 vulnérabilité applicative trouvée.
- 3 points d'entrée désormais protégés par rate limiting (contre 1 avant cette phase).
- 12 menaces du registre STRIDE portent maintenant un statut de vérification explicite avec référence de test.

## 16. Critères de sortie

- [x] Suite de tests d'injection, de contournement d'authentification, de traversée de chemin, d'élévation de privilèges, de rate limiting et d'abus de charge utile.
- [x] Audit XSS manuel des trois frontends.
- [x] Rate limiting étendu au-delà du login.
- [x] Threat model synchronisé avec le code réel, statuts de vérification tracés vers les tests.
- [ ] Test d'intrusion externe (hors de portée d'un agent, nécessite une équipe humaine dédiée).
- [ ] Tests de charge réels (Phase 11, non commencée).

## 17. Conclusion

Cette phase n'a trouvé aucune vulnérabilité applicative exploitable — un résultat qu'il faut interpréter avec la prudence habituelle de ce projet : cela signifie que les classes d'attaque testées ne fonctionnent pas *contre les tests écrits*, pas que le système est invulnérable. Ce que cette phase a produit de concret : un rate limiting réellement plus large qu'avant, un threat model qui dit enfin la vérité sur ce qui est vérifié et ce qui ne l'est pas, et une suite de tests de sécurité qui pourra détecter une régression si l'une de ces protections est un jour affaiblie par erreur.

STATUS: PASS WITH WARNINGS
