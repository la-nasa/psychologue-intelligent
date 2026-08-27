# ADR-001 — Monolithe modulaire API-first pour le pilote

Date : 2026-08-24  
Statut : Accepté pour la phase de fondation

## Contexte

Le produit exige des flux transactionnels entre consentement, conversation, risque, alertes et audit, tout en devant rester extensible et sécurisé. Une architecture distribuée immédiate multiplierait les frontières de confiance, les copies de données sensibles et la charge opérationnelle.

## Décision

Mettre en œuvre un monolithe modulaire avec modules de domaine, interfaces de ports, événements de domaine et une outbox transactionnelle. Les API externes passent par OpenAPI et les intégrations par adaptateurs.

## Conséquences

- Positif : cohérence, test d’intégration simple, déploiement initial réduit, coûts et surface d’attaque maîtrisés.
- Négatif : discipline stricte requise pour éviter les dépendances transverses ; les modules doivent être mesurés avant extraction.
- Alternative rejetée : microservices dès le départ, disproportionnés pour un pilote clinique sans équipe SRE et gouvernance data déjà constituées.

