# PHASE REPORT

Phase: 0 — Audit du projet
Date: 2026-08-24
Objectif: Établir l’état initial, les risques, l’architecture cible et une roadmap avant toute implémentation.

## 1. Travaux réalisés

- Analyse du répertoire de travail, de son état Git et des outils locaux.
- Lecture intégrale de `Psychologue_Intelligent_Architecture.docx` (v1.0, confidentiel, 12–14 mois) et du prompt maître associé.
- Confrontation des exigences à des principes de sécurité, confidentialité et sûreté clinique.
- Définition d’une architecture cible de monolithe modulaire API-first, extractible par domaine.

## 2. Fichiers créés

- `docs/reports/phase-0-audit.md`

## 3. Fichiers modifiés

- Aucun fichier existant. Aucun code applicatif n’a été créé ou modifié.

## 4. Architecture impactée

### Architecture actuelle

Le répertoire ne contient aucun dépôt ni code applicatif : uniquement les dossiers opérationnels `outputs/` et `work/`. Il n’y a ni frontend, ni backend, ni schéma de données, ni pipeline CI/CD, ni configuration, ni tests, ni secret à auditer. Git n’est pas initialisé dans ce répertoire.

### Stack détectée

| Élément | État |
| --- | --- |
| Git | Installé, mais aucun dépôt initialisé |
| Node.js | 24.12.0 installé |
| npm | Installation locale défaillante (`npm-cli.js` introuvable) |
| Python | 3.14.2 installé |
| Docker | CLI 29.1.3 disponible ; configuration utilisateur inaccessible dans cet environnement |
| Base de données / ORM / migrations | Absent |
| Frontend | Absent |
| Backend / API | Absent |
| IA / ML | Absent |
| Tests / CI | Absents |

### Architecture cible proposée

Un monolithe modulaire déployable par conteneurs est recommandé pour le pilote. Les frontières de domaines seront imposées dans le code et par contrats d’événements afin de permettre l’extraction progressive de services sans prématurément distribuer des données de santé.

```text
Web patient / Web clinicien / Administration
                  |
            BFF / API HTTPS
                  |
  Identity | Consent | Patient | Conversation | Assessment
                  |
 Risk & Crisis Engine -> Alert -> Notification -> Audit
                  |
 Policy engine | AI provider ports | Human feedback
                  |
 PostgreSQL (chiffré) | Queue | Object storage | Observabilité
```

Choix de référence à valider à la phase 1 : frontend React/TypeScript, API Python/FastAPI, PostgreSQL, Redis ou équivalent de queue, OpenAPI, migrations Alembic et déploiement Docker. Le choix définitif dépend de la réparabilité de npm et des contraintes d’hébergement, de résidence des données et de l’équipe clinique.

Les fournisseurs IA restent derrière des ports : `LLMProvider`, `EmotionModel`, `RiskModel`, `CrisisModel`. Le moteur de crise, les politiques versionnées et les garde-fous opèrent indépendamment du LLM.

### Flux critiques cibles

1. Un message est validé, normalisé et pseudonymisé au besoin.
2. Le moteur de règles et de crise évalue le message avant toute génération IA.
3. Les signaux, leur version de modèle et la version de politique produisent une décision explicable Vert / Orange / Rouge.
4. Une alerte idempotente est persistée transactionnellement, puis notifiée via une file avec suivi et escalade.
5. Toute action humaine, décision automatisée et accès sensible produisent un audit sans contenu clinique inutile.
6. Les données d’apprentissage ne quittent jamais la production sans opt-in, filtre de confidentialité, anonymisation, revue humaine et approbations documentées.

## 5. Fonctionnalités terminées

L’audit initial et la proposition d’architecture sont terminés. Aucune fonctionnalité produit ne peut raisonnablement être déclarée commencée ou terminée à ce stade.

## 6. Tests exécutés

- Inspection du contenu du workspace.
- Vérification de l’état Git.
- Vérification de disponibilité de Git, Node.js, npm, Python et Docker.
- Extraction et analyse du texte du document Word source.

## 7. Résultats des tests

- Workspace : vide de projet, inspection réussie.
- Git : échec attendu, aucun dépôt.
- Node.js et Python : disponibles.
- npm : échec ; runtime global cassé ou incomplet.
- Docker : binaire détecté, mais accès à sa configuration utilisateur refusé ; aucune validation de daemon ou de conteneur ne peut être revendiquée.

## 8. Bugs détectés

- npm est inutilisable dans l’état actuel.
- Aucun projet, dépôt Git ou dépendance de développement n’est présent.

## 9. Bugs corrigés

- Aucun : la phase 0 ne modifie pas le code, conformément au prompt maître.

## 10. Vulnérabilités détectées

| ID | Menace / risque | Impact | Probabilité | Risque | Mitigation requise | Test |
| --- | --- | --- | --- | --- | --- | --- |
| TM-01 | Décision de crise confiée au LLM | Critique | Moyenne | Critique | Moteur indépendant, règles versionnées, fallback conservateur, supervision humaine | Simulations de crise et défaillances LLM |
| TM-02 | Accès abusif patient-clinicien (BOLA/IDOR) | Critique | Moyenne | Critique | RBAC, relation explicite, contrôles serveur deny-by-default, audit | Tests d’autorisation négatifs |
| TM-03 | Fuite de contenu clinique via logs, IA ou notifications | Critique | Moyenne | Critique | Minimisation, chiffrement, redaction, notifications sans contenu sensible | Tests de fuite de PII/PHI |
| TM-04 | Empoisonnement/prompt injection du LLM | Élevé | Élevée | Critique | Isolation des instructions, validation d’entrée/sortie, aucun outil privilégié, tests adversariaux | Corpus jailbreak/injection |
| TM-05 | Double notification ou perte d’alerte | Critique | Moyenne | Critique | Outbox transactionnelle, idempotence, retry borné, escalade, suivi d’accusé | Tests panne/réessai |
| TM-06 | Réentraînement sur données non consenties ou ré-identifiables | Critique | Moyenne | Critique | Opt-in révocable, anonymisation, dataset lineage, revue humaine, approbation clinique | Tests de révocation et anonymisation |
| TM-07 | Seuils cliniques présentés comme des décisions médicales | Critique | Moyenne | Critique | Politiques configurables, approbation clinique, traçabilité et avertissements UX | Tests de version/rollback |

## 11. Vulnérabilités corrigées

- Aucune vulnérabilité de code : aucun code n’existe encore.
- Les mesures de mitigation ci-dessus sont des exigences de conception obligatoires, pas des contrôles déjà implémentés.

## 12. Dette technique

- Projet à initialiser intégralement : dépôt, conventions, licences, architecture, environnement, CI/CD, tests, migrations, documentation et observabilité.
- Dépendance npm à réparer avant un frontend TypeScript.
- Décisions non techniques à obtenir : juridiction, hébergement, DPO, procédure de crise, canaux autorisés, responsables cliniques et critères d’approbation.

## 13. Décisions techniques

- Monolithe modulaire plutôt que microservices initiaux : moins de surface d’attaque et de complexité opérationnelle, tout en conservant des ports et événements de domaine.
- Base relationnelle transactionnelle pour alertes, consentements et audit ; aucune donnée clinique ne doit dépendre uniquement d’une file ou d’un fournisseur externe.
- Politique clinique hors du code, versionnée, approuvée et réversible.
- LLM interchangeable et strictement non décisionnaire pour les crises.
- L’étude clinique est préparée par des modules de traçabilité, jamais déclarée valide par le logiciel seul.

## 14. Risques restants

- La mise en œuvre d’un produit de santé mentale est bloquée, pour les décisions de déploiement réel, par la validation clinique, éthique, juridique et locale des procédures d’urgence.
- Le document source propose un numéro d’urgence et des seuils : ils ne doivent pas être codés en dur, ni présumés valides dans une juridiction donnée.
- Le document décrit CamemBERT, Bloom/Mixtral et RLHF comme pistes ; leurs performances, licences, hébergement, biais et sécurité doivent être évalués avant sélection.
- Toute promesse de taux de faux négatifs nul ou de bénéfice clinique est un objectif d’étude à mesurer, non une propriété qu’un logiciel peut garantir.

## 15. Métriques

- 0 fichier applicatif existant.
- 0 test applicatif existant.
- 7 risques critiques de conception identifiés dans le registre initial.
- 2 problèmes d’environnement constatés : npm et configuration Docker.

## 16. Critères de sortie

### Gate Phase 0

- [x] Source fonctionnelle examinée.
- [x] État du workspace et de l’environnement vérifié.
- [x] Risques et contradictions documentés.
- [x] Architecture cible et roadmap établies.
- [x] Aucun code produit avant audit.

### Roadmap et gates ultérieurs

| Phase | Résultat attendu | Gate |
| --- | --- | --- |
| 1 — Architecture | ADR, structure, contrats, schéma de données, design system et threat model détaillé | Architecture approuvée et testable |
| 2 — Foundation | Configuration, migrations, auth, RBAC, audit, health checks, CI | Tests fondamentaux et scans passent |
| 3 — User platform | Consentement, profil, onboarding, confidentialité, chat shell | Parcours E2E et contrôles d’accès passent |
| 4 — Assessment | PHQ-9 versionné, scoring, historique et permissions | Cas critiques couverts à 100 % |
| 5–6 — AI/Alert | Ports IA, règles de crise, politiques, alertes et fallback | Simulations de crise, défaillances et audit passent |
| 7 — Clinician | Dashboard, timeline, actions, feedback et recherche | RBAC et tests d’ergonomie/accessibilité passent |
| 8–9 — Learning/Notifications | Opt-in, anonymisation, validation, registry, canaux idempotents | Tests de révocation, approbation, retry et rollback passent |
| 10–14 — Hardening | Sécurité, charge, résilience, E2E et audit final | Aucun risque critique/élevé non traité |
| 15 — RC | Release notes, runbooks, rollback et rapports | Approbations techniques et cliniques requises |

## 17. Conclusion

Le démarrage est sain du point de vue de la procédure : aucune implémentation préalable à l’audit n’a été trouvée ni introduite. L’architecture proposée protège les invariants essentiels (supervision humaine, politiques cliniques configurables, audit, consentement, sécurité des alertes et indépendance du moteur de crise). L’environnement ne permet pas encore de démarrer un frontend Node sans réparer npm, et aucune mise en production clinique ne peut être envisagée sans validation humaine locale.

STATUS: PASS WITH WARNINGS
