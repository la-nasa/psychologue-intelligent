# ADR-013 — Voice Engine avec WebRTC + WebSocket Fallback

Date : 2026-09-13
Statut : **Proposé** — pas encore implémenté (correspond à la Phase 11 de la roadmap originale, non commencée ; aucun module `voice/` dans `server/app/`).
Origine : audit indépendant mené sur la branche `intelligent-psychologist-bdc4b`, fusionné via PR #1. Renuméroté ADR-013 (était `docs/adr/ADR-006-to-010-stack-architecture.md` §5, portait le numéro ADR-010 dans son document d'origine).

## Contexte
La voix est critique pour l'expérience naturelle mais introduit des contraintes de latence strictes, la gestion du réseau dégradé, les permissions navigateur, le streaming bidirectionnel.

## Décision

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

server/app/
├── voice/                  (à créer — Phase 11)
│   ├── webrtc_handler.py
│   ├── websocket_audio.py
│   ├── vad_processor.py
│   ├── stt_streaming.py
│   └── tts_streaming.py
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

## Note de réconciliation (2026-09-13)
Décision non contredite par l'existant — Phase 11 (voix) n'a jamais été commencée sur `server/`, ni sur l'ancien `backend/` v1. Reste à valider au moment de la Phase 11 réelle (ordre de roadmap : après Phase 10, actuellement Phase 15 en cours de préparation — voir décision de numérotation du 2026-09-13).
