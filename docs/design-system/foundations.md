# Fondations du design system

## Direction

Interface clinique calme et précise : surfaces claires, contraste élevé, typographie lisible, espaces généreux et hiérarchie nette. Pas de gradients décoratifs ni de code couleur seul pour signifier une alerte.

## Tokens initiaux

| Catégorie | Valeurs |
| --- | --- |
| Couleur de marque | `ink #17323A`, `teal #256E6A`, `canvas #F7F8F6`, `surface #FFFFFF` |
| Sémantique | succès `#176B4D`, attention `#9A6100`, urgence `#B42318`, erreur `#B42318`, focus `#1D4ED8` |
| Texte | primaire `#172126`, secondaire `#52616B`, inverse `#FFFFFF` |
| Espacement | échelle 4, 8, 12, 16, 24, 32, 48, 64 px |
| Typographie | sans-serif système ; 14 px minimum de corps, 16 px pour les formulaires, interligne 1.5 minimum |
| Rayon / ombre | 8 px / 12 px ; bordures subtiles avant ombre |

## Accessibilité et composants

- WCAG 2.2 AA au minimum : contraste, clavier, focus visible, labels, descriptions d’erreurs et annonce des changements importants.
- Les alertes combinent libellé explicite, icône, couleur et niveau ; rouge n’est jamais la seule indication.
- États requis pour chaque composant : default, hover, focus, active, disabled, loading, empty, error, success.
- Breakpoints de comportement : compact < 640 px, tablette 640–1023 px, bureau ≥ 1024 px. Le mobile priorise le parcours et les actions de sécurité, non la réduction d’un dashboard.
- Les communications de crise doivent être rédigées et validées avec les cliniciens ; aucune formulation définitive n’est introduite au design system.

