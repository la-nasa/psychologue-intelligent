# PHASE 0 ADDENDUM — état réel au 2026-09-18

**Date :** 2026-09-18  
**Complète :** [`phase-0-audit-v2.md`](phase-0-audit-v2.md) (août 2026, alors que la stack V2 n’existait pas encore)  
**Statut :** CONSTAT — aucune validation clinique n’est impliquée

Ce document décrit le dépôt **tel qu’il est**, pas tel qu’un rapport plus ancien le déclarait. En cas de divergence, le code et ses tests font foi.

## 1. Architecture actuelle

Deux stacks coexistent (strangler, ADR-006). Rien n’est détruit.

| Stack | Emplacement | Rôle |
| --- | --- | --- |
| V1 démo | `backend/`, SPA vanilla, SQLite, WSGI | Déploiement Railway actuel. LLM : llama.cpp + Qwen2.5-1.5B Q4 (ADR-005). Latence mesurée : 30 s à > 1 min sur CPU partagé. |
| V2 cible | `server/` FastAPI + PostgreSQL/pgvector + Redis + RabbitMQ ; `frontend/` Next.js 16 | Cœur métier porté : auth/RBAC, conversation SSE, mémoire, personnalisation, Safety Engine, PHQ-9, alertes, clinicien, Patient 360, revue IA, analytics, MLflow best-effort, red team partiel. |

**Trou critique V2 (avant cette itération) :** `server/app/ai/providers/local.py` était un répondeur à gabarits. Le routeur FAST/DEEP existait ; le FAST local n’était pas génératif.

**Voix :** page Next.js (Web Speech API + stream texte). Pas de module `server/app/voice/`, pas de WebRTC/STT/TTS self-hosted (ADR-013 toujours proposé).

## 2. Architecture cible de cette itération

Invariants inchangés : le LLM ne classe jamais une crise ; ORANGE/RED = gabarits ; DEEP externe exige `AI_EXTERNAL` ; OutputSafety après génération ; SAFE_FALLBACK si le modèle est indisponible.

Chemin local hybride (ADR-015) :

1. Serveur OpenAI-compatible (`PI_LLM_BASE_URL`, vLLM ou llama.cpp server) si `health_check` OK.
2. Sinon GGUF in-process (`llama-cpp-python`, `n_gpu_layers` auto).
3. Sinon gabarits `LocalSupportiveResponder` — jamais une fausse assurance.

Cibles de latence (§14 du prompt maître) = **objectifs d’ingénierie**, pas des garanties. Un CPU partagé (Railway V1) ne peut pas honorer un premier token < 1–2 s.

## 3. Écarts

**Déjà livré :** Phases 1–14 V2 (fondation → revue IA), plus analytics / learning / mlops partiels.

**Cette itération :** LLM local génératif hybride, TTFT observé, voix utilisable (navigateur), tests, ADR-015.

**Reporté :** WebRTC + Whisper/TTS GPU, K8s/Helm, Triton, étude clinique / RCT, i18n fr/en complet, k6/Locust, Grafana complet, DVC.

**V1 Railway :** non cassée. La démo CPU ne peut pas honorer les cibles §14 ; une bascule vers V2+GPU reste une décision d’exploitation séparée.

## 4. Risques restants

- Physique CPU : « presque instantané » impossible sans GPU.
- Windows : vLLM = Linux/CUDA (Docker GPU ou llama.cpp wheels).
- Qwen 0.5B CPU : plus rapide, moins nuancé ; OutputSafety et politique une-question restent la ceinture.
- Aucune validation clinique n’a eu lieu.
