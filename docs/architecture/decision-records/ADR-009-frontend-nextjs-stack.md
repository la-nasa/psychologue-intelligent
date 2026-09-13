# ADR-009 — Adoption stack frontend Next.js 16 + React 19.2

Date : 2026-09-13
Statut : **Accepté** (à confirmer après audit du contenu réel de `frontend/` — voir note ci-dessous).
Origine : audit indépendant mené sur la branche `intelligent-psychologist-bdc4b`, fusionné dans `feat/v2` via PR #1. Renuméroté ADR-009 (était `docs/adr/ADR-006-to-010-stack-architecture.md` §1, en collision avec l'ADR-006 déjà accepté de ce dossier).

## Note de réconciliation (2026-09-13)

Ce document a été produit par un audit exécuté indépendamment du travail déjà commité sur `server/` (Phase 0-14, voir `phase-0-audit-v2.md` et `overview-v2.md`). Il ignore que `server/` existait déjà et propose une réécriture complète du frontend. La décision de conserver ou non `frontend/` (Next.js) comme base du frontend V2 est en cours d'audit (contenu réel : appelle-t-il l'API `server/` ou des données factices ?) — ce statut ACCEPTÉ concerne uniquement le choix de **stack technique** (Next.js/React/Tailwind/shadcn), pas l'usage du code déjà écrit sous `frontend/`.

Écart non résolu avec `overview-v2.md` §14 : ce document cible un frontend V2 sous `web/`, alors que le code produit par cet audit a été placé sous `frontend/` en renommant l'ancien SPA vanilla en `frontend-vanilla/`. À trancher séparément.

## Contexte

Le frontend v1 (`frontend-vanilla/`) utilise Vanilla JS/HTML/CSS, ce qui limite la réactivité, le streaming temps réel, la gestion d'état complexe, la réutilisabilité des composants, l'accessibilité et la scalabilité mobile.

## Décision

Adopter la stack suivante pour le frontend V2 :

```text
Next.js 16 (App Router)
React 19.2
TypeScript 5.x
Tailwind CSS
shadcn/ui (composants)
Radix UI (primitives)
TanStack Query (data fetching)
Zod (validation)
React Hook Form (forms)
Framer Motion (animations)
Recharts (visualisation)
Lucide (icônes)
```

## Justification

### Next.js 16
- Server Components pour performance
- Streaming natif pour conversations
- SSR/SSG hybride
- Routing moderne avec App Router
- Optimisations automatiques

### React 19.2
- Support complet des Server Components
- Actions serveur natives
- Améliorations performance
- Meilleure gestion état

### TypeScript
- Typage fort pour sécurité
- Détection erreurs à la compilation
- Meilleure DX
- Documentation auto-générée

### Tailwind + shadcn/ui
- Design system cohérent
- Composants accessibles
- Personnalisation facile
- Maintenance simplifiée

## Conséquences

### Positives
- UX nettement améliorée
- Streaming natif
- Meilleure accessibilité
- Code plus maintenable
- Écosystème riche

### Négatives
- Courbe d'apprentissage
- Build time initial plus long
- Complexité accrue vs Vanilla JS
- Nécessite Node.js récent

### Migration
- Coexistence temporaire ancien/nouveau frontend (`frontend-vanilla/` vs `frontend/`)
- Migration progressive par feature
- API REST existante (`server/`) réutilisée
- WebSocket compatible

## Références
- Next.js Documentation: https://nextjs.org/docs
- React 19 Release Notes
- shadcn/ui: https://ui.shadcn.com
- ADR-001 (Architecture modulaire)
- ADR-006 (Adoption stack V2 — server/, distinct de cet ADR qui ne couvre que le frontend)
- Prompt Maître Section 3 (Stack Technologique)
