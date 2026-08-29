# Design system V2 — fondations

Statut : conception Phase 1. Implémentation en `frontend/packages/design-system/` à partir de la Phase 2 (fondation) puis Phase 3+ (écrans).
Étend `docs/design-system/foundations.md` (v1) — la direction « clinique calme et précise » est conservée et approfondie.
Cible technique : Next.js 16 (App Router), React 19.2, TypeScript strict, Tailwind CSS, shadcn/ui + Radix (primitives accessibles), Framer Motion (micro-animation), Recharts (graphes cliniques).

---

## 1. Intention

Deux publics, deux ambiances, **un seul système** :

- **Espace patient** : un lieu où l'on prend le temps. Calme, spacieux, peu d'éléments à l'écran à la fois, langage humain. Ne doit jamais ressembler à un outil médical anxiogène ni à une messagerie grand public.
- **Espace clinicien / admin** : dense en information mais **lisible en quelques secondes**. Hiérarchie forte, tableaux et graphes précis, aucune décoration.

**Interdits explicites** (règles 51–52 du prompt maître) — le design ne doit ressembler ni à :
- un dashboard IA générique (cartes violettes, dégradés, glow) ;
- un template SaaS générique (hero + 3 features + pricing) ;
- un clone de ChatGPT (bulle grise pleine largeur, avatar rond, curseur clignotant central).

**À éviter** : dégradés décoratifs, glassmorphism partout, animations gratuites, icônes géantes, répétition de cartes identiques, faux effets « futuristes », couleur seule pour signifier un état.

**À rechercher** : blanc tournant généreux, hiérarchie typographique forte, mouvement subtil et fonctionnel, typographie précise, langage visuel apaisé, excellents états vides, faible charge cognitive.

---

## 2. Tokens

Les tokens sont la seule source de vérité. Aucune valeur brute (`#hex`, `16px`) dans un composant.

### 2.1 Couleur

Palette **chaude-neutre** (pas le bleu clinique par défaut), un seul accent, sémantique distincte de l'accent.

```
--color-ink            #17323A   /* texte fort, titres */
--color-ink-soft       #52616B   /* texte secondaire */
--color-canvas         #F7F8F6   /* fond d'app */
--color-surface        #FFFFFF   /* cartes, panneaux */
--color-surface-sunken #EFF1 EE  /* zones en retrait, champs */
--color-border         #E2E5E1   /* filets — toujours avant l'ombre */

--color-accent         #256E6A   /* teal profond — action primaire, liens */
--color-accent-hover   #1F5B58
--color-accent-weak    #E5EFEE   /* fond d'état sélectionné */

/* Sémantique — jamais utilisée comme accent décoratif */
--color-success        #176B4D
--color-attention      #9A6100   /* ORANGE clinique */
--color-critical       #B42318   /* RED clinique / erreur */
--color-info           #1D4ED8   /* focus, information neutre */

/* Sévérité clinique — bandes dédiées, toujours accompagnées d'un libellé + icône */
--sev-green   #176B4D   --sev-green-bg   #E7F1EC
--sev-orange  #9A6100   --sev-orange-bg  #FBF0DE
--sev-red     #B42318   --sev-red-bg     #FBE9E7
--sev-unknown #52616B   --sev-unknown-bg #ECEEEC
```

**Mode sombre** (clinicien de nuit, préférence système) : redéfinir les tokens sous `[data-theme="dark"]` et `@media (prefers-color-scheme: dark)`. `--color-canvas #10201F`, `--color-surface #16302E`, `--color-ink #EAF0EE`. Les bandes de sévérité gardent leur teinte, fond assombri. Aucune couleur définie uniquement dans un bloc `dark`.

**Contraste** : tout texte ≥ WCAG 2.2 AA (4.5:1 corps, 3:1 grand texte). Vérifié en CI (script de contraste sur les paires token).

### 2.2 Typographie

```
--font-sans:  "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
--font-serif: "Source Serif 4", ui-serif, Georgia, serif;   /* accents éditoriaux, titres patient */
--font-mono:  ui-monospace, "SF Mono", "Cascadia Code", monospace;  /* identifiants, horodatages */
```

Échelle (ratio ~1.25, `rem`) :

| Token | Taille / interligne | Usage |
| --- | --- | --- |
| `text-display` | 2.5 / 1.15 | titre d'accueil patient (serif) |
| `text-h1` | 1.75 / 1.25 | titre d'écran |
| `text-h2` | 1.375 / 1.3 | section |
| `text-h3` | 1.125 / 1.4 | sous-section, titre de carte |
| `text-body` | 1.0 / 1.6 | corps (min 16px, jamais moins pour un formulaire) |
| `text-small` | 0.875 / 1.5 | métadonnées, légendes |
| `text-mono` | 0.8125 / 1.5 | id, timestamp |

Poids : 400 (corps), 500 (emphase, labels), 600 (titres). Pas de 700+ (trop agressif pour le contexte).

### 2.3 Espacement, rayon, élévation, mouvement

```
--space: 2 4 8 12 16 24 32 48 64 96   (px, échelle nommée space-1 … space-10)
--radius-sm 6   --radius-md 10   --radius-lg 16   --radius-full 999
--shadow-1: 0 1px 2px rgba(23,50,58,.06), 0 1px 1px rgba(23,50,58,.04)   /* cartes au repos */
--shadow-2: 0 4px 12px rgba(23,50,58,.10)                                /* survol, menus */
--shadow-3: 0 12px 32px rgba(23,50,58,.16)                               /* dialogues */
--motion-fast 120ms   --motion-base 200ms   --motion-slow 320ms
--ease-standard cubic-bezier(.2,0,0,1)
--ease-enter   cubic-bezier(0,0,0,1)
```

**Mouvement** : uniquement fonctionnel — apparition de contenu, changement d'état, feedback d'action. Respecte `prefers-reduced-motion` (bascule sur des transitions d'opacité de 1 frame). Jamais de parallaxe, de « float » permanent, de confetti.

---

## 3. États obligatoires par composant

Chaque composant livré expose et teste : `default, hover, focus-visible, active, disabled, loading, success, error, empty, offline`.

- **focus-visible** toujours visible (anneau `--color-info` 2px + offset), jamais supprimé.
- **loading** : skeleton pour du contenu, spinner en ligne pour une action ; jamais de blocage plein écran.
- **empty** : un vrai message utile (« Aucune alerte en attente — les nouvelles apparaîtront ici en temps réel »), pas une zone vide.
- **error** : message actionnable + moyen de réessayer ; jamais un code brut ni une trace.
- **offline** : bandeau persistant expliquant l'état + ce qui reste possible (§75 du prompt).

---

## 4. Inventaire de composants

### 4.1 Primitives (via Radix / shadcn, re-thématisées)

Button (variants : `primary`, `secondary`, `ghost`, `danger`, `link` ; tailles `sm/md/lg` ; état `loading` avec largeur stable), Input, Textarea (auto-grow), Select, Combobox, Checkbox, Radio, Switch, Slider, Tabs, Accordion, Tooltip, Popover, Dialog, Sheet (mobile), Toast, DropdownMenu, Avatar (initiales, pas de photo par défaut), Badge, Progress, Separator, ScrollArea.

### 4.2 Composants applicatifs — patient

| Composant | Notes |
| --- | --- |
| `AppShell` (patient) | barre latérale minimale (Accueil, Conversation, Objectifs, Confidentialité), langage humain, jamais plus de 4 entrées |
| `Greeting` | « Bonjour {prénom}. Comment vous sentez-vous aujourd'hui ? » — serif, généreux |
| `CheckInCard` | mini check-in (humeur, énergie, stress, sommeil) — curseurs doux, 4 items max, pas de PHQ-9 ici sauf programmé |
| `ConversationView` | en-tête discret (état de session), fil de messages, indicateur « écoute / réfléchit / écrit / parle », zone de saisie, bouton voix, point d'entrée urgence toujours visible |
| `MessageBubble` | **pas** de bulle pleine largeur grise. Patient : aligné fin, fond `--color-accent-weak`, coin. Assistant : aligné début, fond `--color-surface`, filet. Horodatage `text-mono` discret au survol. |
| `StreamingText` | rendu progressif token par token, curseur fin en fin de ligne, pas de saut de layout |
| `TypingIndicator` | 3 points, animation lente, libellé texte pour lecteur d'écran (« l'assistant rédige une réponse ») |
| `SafetyNotice` | encart au-dessus de la conversation : IA hébergée localement / chemin externe si consenti, non-diagnostic, réponse de sécurité validée si risque. Texte validé avec les cliniciens. |
| `GoalCard` | titre, barre de progression sobre, dernière réflexion ; jamais d'objectif imposé |
| `ConsentDialog` | une finalité par bloc, langage clair, fournisseur nommé pour `AI_EXTERNAL`, révocable depuis Confidentialité |
| `EmergencyEntryPoint` | discret mais permanent ; ouvre un panneau avec ressources locales (jamais de numéro codé en dur — configuré par organisation/juridiction) |

### 4.3 Composants applicatifs — clinicien / admin

| Composant | Notes |
| --- | --- |
| `AppShell` (clinicien) | menu court : Aperçu, Patients, Alertes, Patient 360, Conversations, Revue IA, Analytics, Réglages |
| `TodayOverview` | patients actifs, alertes critiques, revues en attente, patients à surveiller, réponses IA non revues, changements récents — chiffres + tendance, pas de « carte marketing » |
| `AlertCenter` | table : sévérité (bande + libellé + icône), heure, patient (pseudonyme), déclencheur, confiance, tendance, SLA (compte à rebours), statut, clinicien assigné. Filtres : sévérité, date, patient, statut, assigné. |
| `AlertRow` / `AlertDetail` | cycle de vie visible (`DETECTED → … → CLOSED`), chaque transition horodatée + acteur + justification |
| `Patient360` | Aperçu, État actuel, Conversations récentes, Mémoire, PHQ-9, Tendance émotionnelle, Risque, Alertes, Objectifs, Progrès, Notes clinicien, Résumé IA. Compréhensible en quelques secondes. |
| `AiSummaryPanel` | résumé généré + **`EvidenceLink`** sur chaque affirmation → ouvre la source (message, score, alerte). Aucune affirmation sans source. |
| `AiReviewCard` | message patient, contexte, réponse IA, mémoire pertinente, analyse de risque → actions `APPROUVER / ÉDITER / REJETER / SIGNALER SÉCURITÉ` + notation 1–5 (empathie, pertinence, personnalisation, compréhension du contexte, sécurité, clarté, utilité) + catégorie de feedback |
| `TrendChart` | Recharts, palette sévérité, pas de 3D, pas d'aire dégradée ; annotation « corrélation, pas diagnostic » sur les tendances longitudinales |
| `ClinicianPerfPanel` | revues faites, temps moyen, qualité de feedback, taux d'accord, revues en attente, temps de réponse alerte — cadré « amélioration / charge de travail », jamais surveillance punitive (§40) |
| `DataTable` | tri, filtre, pagination **cursor-based**, densité réglable, sélection, export ; virtualisation au-delà de ~100 lignes |

### 4.4 Composants voix _(Phase 11)_

| Composant | Notes |
| --- | --- |
| `VoiceButton` | états : `idle`, `requesting-permission`, `listening`, `processing`, `thinking`, `speaking`, `interrupted`, `reconnecting`, `error` — chacun avec libellé texte + forme distincte, pas seulement une couleur |
| `MicPermissionPrompt` | explication avant la demande navigateur ; indication claire d'enregistrement ; lien vers la politique de rétention audio |
| `LiveTranscript` | transcription partielle en gris, finale en `--color-ink` ; jamais de répétition de phrase |
| `AudioLevelMeter` | retour visuel discret du niveau micro |
| `BargeInHint` | « vous pouvez m'interrompre » ; l'interruption coupe le TTS immédiatement |

---

## 5. Accessibilité (WCAG 2.2 AA minimum)

- HTML sémantique d'abord, ARIA seulement si nécessaire.
- Navigation clavier complète, ordre de tabulation logique, gestion du focus à chaque changement de vue (le titre d'écran reçoit le focus).
- `aria-live="polite"` sur le fil de conversation et les messages système ; `assertive` réservé aux alertes de sécurité.
- Cibles tactiles ≥ 44×44 px.
- Contraste vérifié en CI. Zoom 200 % sans perte de contenu ni scroll horizontal.
- Toute information d'état = libellé + forme/icône + couleur (jamais couleur seule).

---

## 6. Responsive

Breakpoints de comportement (repris v1) : `compact < 640px`, `tablette 640–1023px`, `bureau ≥ 1024px`.

- **Mobile-first pour le patient** : la conversation (texte et voix) doit être excellente sur mobile ; conçue séparément, pas un desktop rétréci. Actions de sécurité toujours atteignables au pouce.
- **Clinicien sur mobile** : priorité au parcours (voir une alerte, l'accuser, ouvrir un patient), pas la réduction d'un dashboard. `Sheet` plutôt que `Dialog`, tables en mode carte.
- Le `<body>` ne défile jamais horizontalement ; tout contenu large (table, graphe) défile dans son propre conteneur `overflow-x:auto`.

---

## 7. Internationalisation

- `next-intl` (ou équivalent), `fr` et `en` dès la Phase 2, chaînes externalisées à 100 % (aucun texte en dur — la v1 est tout en français en dur, à corriger au portage).
- Format de date/heure, pluriels, direction gérés par la lib.
- Le moteur vocal identifie la langue (`SpeechToTextProvider` renvoie `language`) ; l'UI peut proposer de basculer.
- Les variantes régionales (français/anglais camerounais, code-switching) sont un sujet d'**évaluation** (Phase 22), pas une promesse d'interface.

---

## 8. Livrable Phase 1 vs Phase 2

- **Phase 1 (ce document)** : tokens, principes, inventaire, états, règles a11y/responsive/i18n. Revu et acté.
- **Phase 2** : `frontend/packages/design-system/` — tokens en CSS variables + config Tailwind, primitives thématisées, Storybook (ou équivalent) avec chaque état, tests de contraste et d'accessibilité en CI.
- **Phases 3+** : composants applicatifs au fil des écrans.
