# Déploiement Railway (démonstration/pilote technique)

Ce document décrit le déploiement réellement effectué sur Railway, y compris deux comportements de plateforme non documentés découverts en le faisant — pas une procédure théorique copiée d'un tutoriel. **Ce déploiement sert de démonstration technique, pas de pilote avec de vrais patients** : voir `production-readiness.md` pour l'écart complet restant.

## Ce qui est déployé

- Un unique service Railway (`web`) construit depuis [`la-nasa/psychologue-intelligent`](https://github.com/la-nasa/psychologue-intelligent) (branche `main`) via Nixpacks/Railpack, sans étape de build supplémentaire (zéro dépendance runtime, voir ADR-003).
- Point d'entrée : [`scripts/serve.py`](../../scripts/serve.py) — reprend l'assemblage WSGI de `scripts/dev_server.py` (API + les trois frontends statiques sur une seule origine) mais écoute sur `0.0.0.0:$PORT` avec un serveur WSGI threadé, au lieu du bind `127.0.0.1` fixe et non threadé du serveur de développement.
- Un volume persistant (`web-data`) monté sur `/data`, avec `PI_DATABASE_PATH=/data/psychologue-intelligent.db`.
- Health check configuré sur `/health/live` (ne touche jamais la base de données, voir `backend/app/http.py`).
- En-têtes de sécurité complets déjà en place côté application (voir `docs/security/security-assessment-report.md`) ; Railway termine le TLS en périphérie, ce qui ferme la ligne « TLS : aucun » de `production-readiness.md` pour ce déploiement précis (le reste de l'écart production-readiness demeure entier).

## Provisionner les comptes CLINICIAN/ADMIN sur ce déploiement

`scripts/provision_user.py` (usage local, interactif) ne peut pas être exécuté contre la base persistante d'un déploiement Railway une fois celui-ci en ligne : voir la Section « Piège n°1 » ci-dessous. À la place, [`scripts/bootstrap_privileged_users.py`](../../scripts/bootstrap_privileged_users.py) tourne au démarrage réel du conteneur et est idempotent (il ignore silencieusement un rôle déjà provisionné) :

```
PI_BOOTSTRAP_CLINICIAN_EMAIL=...
PI_BOOTSTRAP_CLINICIAN_PASSWORD=...
PI_BOOTSTRAP_ADMIN_EMAIL=...
PI_BOOTSTRAP_ADMIN_PASSWORD=...
```

Le secret TOTP de chaque compte créé est affiché une seule fois dans les logs de démarrage du déploiement (jamais persisté ailleurs que dans la table `users`) — à récupérer immédiatement, il ne réapparaîtra pas. Sans flux de réinitialisation MFA (absent par conception, voir les rapports de phase antérieurs), une perte de ce secret impose de recréer le compte.

## Piège n°1 : une pre-deploy command Railway ne partage pas le volume du conteneur

**Symptôme observé** : un compte provisionné via `preDeployCommand` (`python scripts/provision_user.py ...`) se crée avec succès (le log de log l'affiche), mais est ensuite introuvable par l'application réelle — `verify_login.py` échoue avec « invalid credentials », et re-enregistrer le même e-mail via `POST /api/v1/auth/register` réussit (ce qui ne devrait pas être possible si le compte existait vraiment).

**Cause** : la pre-deploy command Railway s'exécute dans un système de fichiers séparé du conteneur réellement servi, sans le volume persistant monté. `PI_DATABASE_PATH=/data/...` y crée donc une base SQLite neuve et jetable, invisible de l'application réelle une fois démarrée.

**Correction adoptée** : ne jamais utiliser `preDeployCommand` pour une opération qui doit toucher les données persistantes. `scripts/bootstrap_privileged_users.py` s'exécute à la place dans la vraie `startCommand`, donc dans le même conteneur et le même volume que le serveur — et son idempotence le rend sûr à laisser en place en permanence plutôt que de devoir le retirer après un seul usage.

## Piège n°2 : `railway.toml` du dépôt écrase silencieusement un `startCommand` fixé via l'API/dashboard

**Symptôme observé** : `startCommand` modifié via l'API Railway (confirmé par `get-service-config`, qui renvoie bien la nouvelle valeur), puis un déploiement déclenché — mais le conteneur démarre avec l'ancienne commande, sans aucune erreur ni avertissement. Reproduit même avec une commande triviale (`sh -c "echo TEST && ..."`) : l'`echo` n'apparaît jamais dans les logs.

**Cause** : `railway.toml`, présent à la racine du dépôt et versionné, définit `[deploy].startCommand`. Ce fichier fait autorité à chaque déploiement et écrase toute valeur fixée dynamiquement via l'API ou le dashboard pour ce champ, sans le signaler.

**Correction adoptée** : toute modification durable de `startCommand` doit être faite dans `railway.toml` lui-même, commitée et poussée — jamais seulement via l'API. C'est là qu'est définie la commande actuelle : `python scripts/bootstrap_privileged_users.py; python scripts/serve.py` (le `;` plutôt que `&&` est délibéré : un échec du bootstrap ne doit jamais empêcher le serveur de démarrer).

## Piège n°3 (le plus sérieux) : un volume « créé avec succès » peut ne pas être réellement monté

**Symptôme observé** : l'outil d'attachement de volume a renvoyé un message de succès explicite (« Volume web-data has been created and mounted to your web service at /data »), mais `get-service-config` ne faisait apparaître **aucune** clé `volumeMounts` par la suite. Conséquence réelle : chaque redéploiement repartait d'une base de données vide, silencieusement — des comptes provisionnés avec succès à un déploiement donné n'existaient plus au suivant, sans aucune erreur nulle part.

**Détection** : ne jamais faire confiance au seul message de confirmation d'un outil d'infrastructure pour une opération d'attachement de volume. Vérifier positivement via `get-service-config` que `volumeMounts` contient bien l'identifiant du volume attendu, **et** vérifier la persistance réelle en écrivant une donnée, en déclenchant un redéploiement complet, puis en relisant cette donnée — pas seulement en relisant dans le même déploiement en cours.

**Correction adoptée** : recréation du volume avec l'outil dédié d'attachement de volume (pas l'agent générique), puis vérification positive en trois temps : (1) `volumeMounts` présent dans `get-service-config`, (2) les variables `RAILWAY_VOLUME_ID`/`RAILWAY_VOLUME_MOUNT_PATH` injectées automatiquement apparaissent bien dans `list-variables`, (3) un compte créé à un déploiement survit un redéploiement complet suivant (`scripts/bootstrap_privileged_users.py` affiche « already exists, skipping » au lieu de recréer le compte). Les trois conditions sont maintenant vérifiées et vraies pour ce déploiement.

**Conséquence acceptée** : toutes les données créées avant cette correction (comptes de test, y compris les tout premiers comptes CLINICIAN/ADMIN provisionnés) ont été perdues silencieusement lors du redéploiement suivant. Sans conséquence ici — c'était uniquement des données de démonstration —, mais ce serait un incident sérieux avec de vraies données patient, ce qui est une raison de plus documentée pour ne pas utiliser ce déploiement au-delà d'une démonstration technique tant que ce point n'a pas été re-vérifié indépendamment avant tout pilote réel.

## Limites qui restent, propres à ce déploiement

- SQLite sur un unique volume, une seule instance (`numReplicas: 1`) : aucune haute disponibilité, aucune sauvegarde automatisée configurée côté Railway.
- Aucun ordonnanceur ne déclenche `scripts/retry_notifications.py` sur ce déploiement (voir `runbook.md`) : les notifications en échec s'accumulent sans reprise tant que ce n'est pas mis en place.
- `LogNotificationProvider` reste le seul fournisseur : aucune notification n'atteint réellement un canal externe sur ce déploiement.
