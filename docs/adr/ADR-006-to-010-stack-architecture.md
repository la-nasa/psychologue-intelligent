# ADR-006: Adoption Stack Frontend Next.js 16 + React 19.2

## Statut
ACCEPTÉ

## Contexte
Le frontend actuel utilise Vanilla JS/HTML/CSS, ce qui limite :
- La réactivité et l'expérience utilisateur
- Le streaming temps réel
- La gestion d'état complexe
- La réutilisabilité des composants
- L'accessibilité
- La scalabilité mobile

## Décision
Adopter la stack suivante pour le frontend :

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
- Coexistence temporaire ancien/nouveau frontend
- Migration progressive par feature
- API REST existante réutilisée
- WebSocket compatible

## Références
- Next.js Documentation: https://nextjs.org/docs
- React 19 Release Notes
- shadcn/ui: https://ui.shadcn.com
- ADR-001 (Architecture modulaire)
- Prompt Maître Section 3 (Stack Technologique)

---

# ADR-007: Multi-Tenancy dès Phase 2

## Statut
ACCEPTÉ

## Contexte
Le système doit supporter plusieurs organisations (cliniques, hôpitaux, cabinets) avec isolation stricte des données.

## Décision
Implémenter le multi-tenancy dès la Phase 2 (Foundation) avec :

```text
Niveau d'isolation: Database-level isolation logique
Clé de partitionnement: organization_id sur toutes les tables
RBAC: Rôles scoped par organisation
Secrets: Séparés par organisation
Configuration: Par organisation
```

## Schéma d'isolation

```sql
-- Toutes les tables critiques auront organization_id
organizations (id, name, slug, settings, created_at)
users (id, organization_id, email, role, ...)
patients (id, organization_id, user_id, ...)
conversations (id, organization_id, patient_id, ...)
alerts (id, organization_id, patient_id, ...)
...
```

## Middleware d'isolation
Chaque requête API valide :
1. Authentification utilisateur
2. Récupération organisation depuis token/session
3. Injection organization_id dans tous les queries
4. Vérification accès resource-specific

## Conséquences

### Positives
- Isolation forte dès le début
- Pas de refactor majeur ultérieur
- Ready pour déploiement multi-cliniques
- Compliance facilitée (RGPD, HIPAA)

### Négatives
- Complexité query accrue
- Tests plus élaborés
- Indexation supplémentaire requise

## Migration
- Script migration pour ajouter organization_id
- Valeur par défaut pour données existantes
- Validation stricte en production

---

# ADR-008: MLflow pour Model Registry & MLOps

## Statut
ACCEPTÉ

## Contexte
Le système nécessite un suivi rigoureux des modèles IA :
- Versioning
- Expérimentation
- Évaluation
- Approbation clinique
- Déploiement contrôlé
- Rollback

## Décision
Utiliser MLflow comme plateforme MLOps centrale :

```text
MLflow Tracking: Expériences, paramètres, métriques
MLflow Models: Packaging, formats, dependencies
MLflow Registry: Versioning, stages, transitions
MLflow Projects: Pipelines reproductibles
```

## Stages du Model Registry

```text
EXPERIMENTAL → STAGING → SHADOW → CANARY → PRODUCTION → RETIRED
```

## Intégration Backend

```python
# backend/app/mlops/registry.py
class ModelRegistry:
    async def register_model(...)
    async def promote_model(...)
    async def get_production_model(...)
    async def rollback(...)
    
# backend/app/mlops/tracking.py
class ExperimentTracker:
    async def log_experiment(...)
    async def log_metrics(...)
    async def compare_models(...)
```

## Pipeline MLOps

```text
Entraînement
 ↓
Évaluation offline
 ↓
MLflow Logging
 ↓
Validation sécurité
 ↓
Validation clinique
 ↓
Shadow deployment
 ↓
Canary (5% traffic)
 ↓
Production (100%)
 ↓
Monitoring continu
```

## Infrastructure

```yaml
# infrastructure/mlflow/docker-compose.yml
mlflow-tracking-server:
  image: ghcr.io/mlflow/mlflow
  ports: ["5000:5000"]
  environment:
    - MLFLOW_S3_ENDPOINT_URL
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
  volumes:
    - mlflow_data:/opt/mlflow/data
    
mlflow-registry:
  depends_on: [mlflow-tracking-server]
```

## Conséquences

### Positives
- Traçabilité complète
- Reproductibilité
- Governance clinique facilitée
- Rollback rapide
- Comparaison modèles

### Négatives
- Infrastructure supplémentaire
- Courbe d'apprentissage équipe
- Stockage artifacts (S3/MinIO requis)

## Alternatives rejetées
- **Weights & Biases**: Cloud-only, moins contrôle
- **Neptune**: Coût élevé à scale
- **Solution maison**: Trop complexe, reinvent wheel

---

# ADR-009: Architecture Hybride LLM

## Statut
ACCEPTÉ

## Contexte
Besoin de flexibilité entre :
- Performance/coût (API cloud)
- Confidentialité/contrôle (local)
- Résilience (fallback)

## Décision
Implémenter une architecture hybride :

```text
Routeur intelligent →
  ├─ Modèles locaux (vLLM) pour données sensibles
  ├─ API cloud (OpenAI/Anthropic) pour complexité
  └─ Fallback CPU pour résilience
```

## Stratégie de routage

```python
class LLMRouter:
    def select_provider(self, request):
        if request.contains_sensitive_data():
            return LOCAL_MODEL
            
        if request.requires_deep_reasoning():
            return CLOUD_DEEP_MODEL
            
        if request.is_simple():
            return FAST_MODEL  # local ou cloud
            
        return STANDARD_MODEL
```

## Configuration

```yaml
llm:
  providers:
    local:
      type: vllm
      endpoint: http://vllm:8000
      models: [mistral-7b, llama-3-8b]
      fallback: true
      
    cloud_standard:
      type: openai
      model: gpt-4o-mini
      fallback: false
      
    cloud_deep:
      type: anthropic
      model: claude-sonnet-4
      fallback: false
      
  routing:
    default: local
    sensitive_data: local
    complex_reasoning: cloud_deep
    low_latency: local
```

## Conséquences

### Positives
- Flexibilité maximale
- Confidentialité préservée
- Coûts optimisés
- Résilience améliorée

### Négatives
- Complexité opérationnelle
- Monitoring multiple
- Latence variable

---

# ADR-010: Voice Engine avec WebRTC + WebSocket Fallback

## Statut
ACCEPTÉ

## Contexte
La voix est critique pour l'expérience naturelle mais introduit :
- Contraintes latence strictes
- Gestion réseau dégradé
- Permissions navigateur
- Streaming bidirectionnel

## Décision
Architecture Voice Engine :

```text
WebRTC (primaire) pour audio streaming
WebSocket (fallback) si WebRTC indisponible
VAD local (Web Audio API) pour détection silence
STT streaming (Whisper/vLLM)
TTS streaming (cloud ou local)
Barge-in supporté
```

## Composants

```text
frontend/
├── voice/
│   ├── VoiceSessionManager.tsx
│   ├── AudioCapture.ts
│   ├── VAD.ts
│   ├── WebRTCClient.ts
│   ├── WebSocketAudioClient.ts
│   └── useVoiceState.ts

backend/
├── app/
│   ├── voice/
│   │   ├── webrtc_handler.py
│   │   ├── websocket_audio.py
│   │   ├── vad_processor.py
│   │   ├── stt_streaming.py
│   │   └── tts_streaming.py
```

## Objectifs latence

```text
UI interaction       < 100 ms
Partial transcription < 300–500 ms
First AI text         < 1–2 s
First audio           < 1–2 s
Normal turn           < 2–3 s
```

## Conséquences

### Positives
- Latence minimale
- Expérience conversationnelle naturelle
- Fallback robuste
- Barge-in (interruption) supporté

### Négatives
- Complexité significative
- Testing approfondi requis
- GPU nécessaire pour STT/TTS temps réel

---

Date: 2025-01-XX
Auteur: Architecte Système
Approbateurs: Lead Engineer, Clinical Lead, Security Officer
