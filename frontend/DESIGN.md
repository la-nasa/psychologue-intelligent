# Design System: Mensana

## 1. Visual Theme & Atmosphere

A quiet listening room, not a marketing landing page. Warm paper canvas, slate ink, one desaturated sage-teal accent. Density is Daily App Balanced (4). Variance is Offset Asymmetric on entry screens (login, home) and Predictable Symmetric in session and data tools. Motion is Fluid CSS (3–4): message fade-ins, hover, tactile press — never perpetual loops, GSAP pinning, magnetic buttons, or particle effects. The product is clinical-support software; calm is a safety feature.

## 2. Color Palette & Roles

- **Warm Paper** (`hsl(36 22% 97%)` / `#F8F6F2`) — Canvas
- **Porcelain** (`#FFFFFF`) — Elevated surfaces when hierarchy needs a lift
- **Slate Ink** (`hsl(215 22% 16%)` / `#202830`) — Primary text (never `#000000`)
- **Quiet Steel** (`hsl(215 10% 42%)`) — Secondary text, metadata
- **Whisper Line** (`hsl(30 14% 86%)`) — 1px borders
- **Sage Deep** (`hsl(192 28% 28%)` / `#345A63`) — Single accent: CTAs, active nav, focus ring
- **Sage Wash** (`hsl(192 18% 93%)`) — Selected chips, nav active fill
- **Signal Rose** (`hsl(2 52% 44%)`) — Destructive and RED alerts only
- **Olive Confirm** (`hsl(152 28% 32%)`) — Success, resolved
- **Clay Warning** (`hsl(32 58% 40%)`) — ORANGE, SLA caution

Dark theme keeps the same roles on charcoal navy (`hsl(210 22% 8%)`), with Sage Deep lightened to `hsl(186 22% 62%)`. No purple, no neon, no dual warm/cool gray mix.

## 3. Typography Rules

- **Display / UI:** Geist Sans — tracking-tight, hierarchy via weight (500–600) not shouting scale. Page titles `text-2xl` to `text-3xl`.
- **Body:** Geist Sans, `leading-relaxed`, conversation assistant copy `text-[15px]` / 1.65 line-height, max ~65ch.
- **Mono:** Geist Mono — scores, timestamps, SLA, PHQ-9 totals.
- **Banned:** Inter, generic serifs, gradient-filled headlines, emoji.

## 4. Component Stylings

- **Buttons:** Radius 12px. Primary Sage Deep fill, no outer glow. Active: `scale-[0.98]`. Min tap 40–44px.
- **Cards:** Used only when elevation separates a task from the canvas. Prefer `divide-y` lists for queues (alerts, patients, history). Radius 16px, tinted diffusion shadow.
- **Chat:** Patient message: compact Sage Deep bubble, right. Assistant: no bubble — paper block, left, generous leading. Safety cue is a quiet caption, not a banner scream unless RED template.
- **Inputs:** Label above, helper optional, error below. Focus ring Sage Deep. No floating labels.
- **Loaders:** Skeleton bars matching layout. Conversation uses three muted dots, paused if reduced motion.
- **Empty states:** One icon (stroke 1.5), one sentence, one action.

## 5. Layout Principles

- App chrome: 15.5rem sidebar, 3.5rem header, content `max-w-3xl` (session) / `max-w-5xl` (queues).
- Login: editorial split (anchor left, form right). Collapse to single column below 768px.
- Home: one primary resume action, secondary voice/check-in as text rows, goals as a list — not three equal feature cards.
- Clinician overview: metric strip with dividers, not a four-card grid.
- Full-height shells use `100dvh`, not `h-screen`.
- Patient mobile: bottom tab bar (Accueil, Parler, Voix, Historique, Compte). Staff roles keep hamburger drawer.

## 6. Motion & Interaction

- Transitions: `cubic-bezier(0.16, 1, 0.3, 1)` on color/opacity/transform only.
- Stagger lists with CSS `animation-delay` under 240ms; honor `prefers-reduced-motion` and the in-app reduced-motion setting.
- No infinite pulse on clinical surfaces. Voice listening uses a slow breathing scale that stops when idle.

## 7. Anti-Patterns (Banned)

No emojis, Inter, pure black, neon glows, oversized H1, 3-equal marketing cards, Awwwards GSAP, custom cursors, “Elevate / Seamless / Unleash”, fake 99.99% stats, claiming the product is a psychologist, Unsplash, overlapping layers as decoration.
