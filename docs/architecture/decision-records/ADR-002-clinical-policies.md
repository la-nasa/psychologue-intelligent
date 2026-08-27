# ADR-002 — Politiques cliniques versionnées hors du code

Date : 2026-08-24  
Statut : Accepté pour la phase de fondation

## Décision

Les seuils, SLA, escalades, contacts d’urgence, canaux et exigences de revue sont des politiques de données versionnées par environnement. Leur cycle de vie comporte création, tests de simulation, approbation clinique, activation, audit et rollback.

## Conséquences

Le code fournit le moteur déterministe et les validations de schéma ; il ne contient aucun numéro d’urgence, seuil clinique final ou procédure propre à un pays. Une modification reste inactive tant qu’elle n’est pas approuvée par les rôles requis.

