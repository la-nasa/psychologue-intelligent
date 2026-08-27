# ADR-003 — Fondation sans dépendance réseau

Date : 2026-08-24  
Statut : Accepté provisoirement pour la phase 2

## Contexte

L’environnement ne peut ni résoudre ni joindre PyPI et l’installation npm système est incomplète. Les bibliothèques de production prévues ne peuvent donc pas être téléchargées ni auditées.

## Décision

Construire la fondation exécutable avec la bibliothèque standard Python : WSGI, SQLite pour développement/test, migrations SQL explicites, `hashlib.pbkdf2_hmac`, TOTP HMAC, sessions opaques et `unittest`. Aucune dépendance applicative externe n’est ajoutée.

## Conséquences

Cette décision fournit une base réellement exécutable et testée sans simuler de sécurité. SQLite et le rate limiting mémoire ne sont toutefois pas admissibles à un déploiement clinique multi-instance : la phase de déploiement devra sélectionner et tester PostgreSQL, une limite distribuée et une gestion de secrets avant pilote.

