# ADR-004 — Moteur de crise : combinaison des signaux et format de politique

Date : 2026-08-26
Statut : Accepté pour la phase 5–6

## Décision

Le détecteur de crise (`backend/app/crisis.py`) évalue toujours un moteur de règles versionné, indépendamment de la disponibilité ou de la confiance du modèle de risque. Les deux signaux sont combinés par un maximum sur le score et un minimum sur la confiance : un modèle sur-confiant ne peut jamais faire baisser un signal de règle, et l'indisponibilité du modèle ne fait jamais basculer la décision vers un niveau moins prudent. Un échec du modèle est capturé, journalisé et traité comme un signal dégradé (confiance plafonnée), jamais comme une exception qui interromprait l'évaluation.

Les politiques cliniques (`config/policies/crisis-policy-v1.json`) et les règles (`crisis-rules-v1.json`) sont des fichiers JSON versionnés, chargés et validés au démarrage, pas des constantes dans le code. JSON a été choisi plutôt que YAML pour rester cohérent avec la fondation sans dépendance de l'ADR-003 (aucun analyseur YAML dans la bibliothèque standard) ; la structure reste équivalente à celle proposée par le prompt maître (seuils, SLA, revue humaine, canaux, contacts d'urgence, approbation).

Le chargeur refuse de démarrer une politique hors de l'environnement `development` si elle n'a pas `approved_by` et `approved_at` renseignés.

## Conséquences

- Aucune décision de crise ne dépend uniquement du LLM ou d'un seul modèle : TH-05 du threat model reste couvert par construction, pas seulement par convention.
- Modifier un seuil clinique nécessite d'éditer un fichier versionné et auditable, jamais le code applicatif.
- Limite assumée : le moteur de règles reste une liste de termes de développement (`rules-dev-1`), pas un corpus clinique validé. Il doit être remplacé et approuvé avant tout pilote réel.
- Limite assumée : la notification associée à une alerte retente de façon synchrone et bornée (3 tentatives) dans l'appel courant. Il n'existe pas encore d'outbox transactionnelle ni de file différée/DLQ ; TH-06 n'est donc que partiellement couvert tant que l'infrastructure de la phase 9 n'existe pas.
