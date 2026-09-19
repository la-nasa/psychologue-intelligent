"""Génère le tutoriel PDF Mensana (captures + mode d'emploi + résultats de tests)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ROOT / "Mensana-tutoriel-complet.pdf"

NAVY = colors.HexColor("#0F172A")
INK = colors.HexColor("#1E293B")
MUTED = colors.HexColor("#475569")
LINE = colors.HexColor("#CBD5E1")
ACCENT = colors.HexColor("#5B9BD5")
WARN = colors.HexColor("#B45309")
OK = colors.HexColor("#047857")
SOFT = colors.HexColor("#F8FAFC")
CREAM = colors.HexColor("#EEF4FA")


def _register_fonts() -> tuple[str, str]:
    regular = Path(r"C:\Windows\Fonts\segoeui.ttf")
    bold = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    if regular.is_file() and bold.is_file():
        pdfmetrics.registerFont(TTFont("UI", str(regular)))
        pdfmetrics.registerFont(TTFont("UI-Bold", str(bold)))
        return "UI", "UI-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = _register_fonts()


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}
    s["cover_kicker"] = ParagraphStyle(
        "cover_kicker", parent=base["Normal"], fontName=FONT, fontSize=10,
        textColor=ACCENT, tracking=1.2, alignment=TA_CENTER, spaceAfter=8,
    )
    s["cover_title"] = ParagraphStyle(
        "cover_title", parent=base["Title"], fontName=FONT_B, fontSize=28,
        textColor=NAVY, alignment=TA_CENTER, leading=34, spaceAfter=10,
    )
    s["cover_sub"] = ParagraphStyle(
        "cover_sub", parent=base["Normal"], fontName=FONT, fontSize=12,
        textColor=MUTED, alignment=TA_CENTER, leading=18, spaceAfter=6,
    )
    s["h1"] = ParagraphStyle(
        "h1", parent=base["Heading1"], fontName=FONT_B, fontSize=16,
        textColor=NAVY, spaceBefore=16, spaceAfter=8, leading=20,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=base["Heading2"], fontName=FONT_B, fontSize=13,
        textColor=NAVY, spaceBefore=12, spaceAfter=6, leading=17,
    )
    s["h3"] = ParagraphStyle(
        "h3", parent=base["Heading3"], fontName=FONT_B, fontSize=11.5,
        textColor=INK, spaceBefore=8, spaceAfter=4, leading=15,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base["Normal"], fontName=FONT, fontSize=10,
        textColor=INK, alignment=TA_JUSTIFY, leading=14.5, spaceAfter=7,
    )
    s["caption"] = ParagraphStyle(
        "caption", parent=base["Normal"], fontName=FONT, fontSize=8.5,
        textColor=MUTED, alignment=TA_CENTER, leading=11, spaceBefore=3, spaceAfter=12,
    )
    s["warn"] = ParagraphStyle(
        "warn", parent=base["Normal"], fontName=FONT, fontSize=9.5,
        textColor=WARN, leading=13.5, alignment=TA_LEFT, spaceAfter=8,
    )
    s["ok"] = ParagraphStyle(
        "ok", parent=base["Normal"], fontName=FONT, fontSize=9.5,
        textColor=OK, leading=13, spaceAfter=4,
    )
    s["small"] = ParagraphStyle(
        "small", parent=base["Normal"], fontName=FONT, fontSize=8.5,
        textColor=MUTED, leading=12, spaceAfter=4,
    )
    s["toc"] = ParagraphStyle(
        "toc", parent=base["Normal"], fontName=FONT, fontSize=10.5,
        textColor=INK, leading=16, spaceAfter=2,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=base["Normal"], fontName=FONT, fontSize=8.5,
        textColor=INK, leading=11,
    )
    s["cellb"] = ParagraphStyle(
        "cellb", parent=base["Normal"], fontName=FONT_B, fontSize=8.5,
        textColor=NAVY, leading=11,
    )
    s["footer"] = ParagraphStyle(
        "footer", parent=base["Normal"], fontName=FONT, fontSize=8,
        textColor=MUTED, alignment=TA_CENTER,
    )
    return s


def shot(name: str, caption: str, st: dict[str, ParagraphStyle], width: float = 155 * mm):
    path = ASSETS / name
    if not path.is_file():
        return [Paragraph(f"[Capture manquante : {name}]", st["warn"])]
    img = Image(str(path), width=width, height=width * 0.52, kind="proportional")
    img.hAlign = "CENTER"
    # Keep original aspect
    from PIL import Image as PILImage

    with PILImage.open(path) as im:
        w, h = im.size
    ratio = h / w if w else 0.56
    img = Image(str(path), width=width, height=min(width * ratio, 105 * mm))
    img.hAlign = "CENTER"
    return [KeepTogether([img, Paragraph(caption, st["caption"])])]


def bullets(items: list[str], st: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(x, st["body"]), leftIndent=8, value="•") for x in items],
        bulletType="bullet",
        start="•",
        leftIndent=14,
        bulletFontName=FONT,
        bulletFontSize=9,
        spaceAfter=8,
    )


def table(rows: list[list[str]], st: dict[str, ParagraphStyle], col_widths: list[float] | None = None):
    data = [[Paragraph(c, st["cellb"] if i == 0 or j == 0 else st["cell"]) for j, c in enumerate(row)] for i, row in enumerate(rows)]
    # header row uses cellb for all
    data[0] = [Paragraph(c, st["cellb"]) for c in rows[0]]
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), FONT_B),
                ("BACKGROUND", (0, 1), (-1, -1), SOFT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SOFT, CREAM]),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    # Re-style header paragraphs to white
    data[0] = [Paragraph(f"<font color='white'>{c}</font>", st["cellb"]) for c in rows[0]]
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, -1), SOFT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SOFT, CREAM]),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def header_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 12 * mm, A4[0], 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont(FONT, 8)
    canvas.drawString(18 * mm, A4[1] - 7.5 * mm, "Mensana — tutoriel d'utilisation")
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 7.5 * mm, "Démonstration technique — 19 septembre 2026")
    canvas.setFillColor(LINE)
    canvas.rect(0, 0, A4[0], 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT, 8)
    canvas.drawString(18 * mm, 4 * mm, "Ne remplace pas un psychologue. En urgence : 111, 112 ou 115.")
    canvas.drawRightString(A4[0] - 18 * mm, 4 * mm, f"{doc.page}")
    canvas.restoreState()


def build() -> None:
    st = styles()
    story = []

    # --- Couverture ---
    story.append(Spacer(1, 38 * mm))
    story.append(Paragraph("PLATEFORME D'ACCOMPAGNEMENT", st["cover_kicker"]))
    story.append(Paragraph("Mensana", st["cover_title"]))
    story.append(Paragraph("Tutoriel d'utilisation complet", st["cover_sub"]))
    story.append(Paragraph(
        "Guide pas à pas de l'application V2 (interface web + API FastAPI), "
        "avec captures d'écran réelles de la démonstration Railway, résultats de tests "
        "et propositions d'amélioration.",
        st["cover_sub"],
    ))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "<b>Avertissement.</b> Mensana est un espace d'écoute assisté par un modèle de langage "
        "local. Ce n'est <b>pas</b> un dispositif médical, <b>pas</b> un psychologue, "
        "<b>pas</b> un service d'urgence, et la démonstration en ligne n'est <b>pas</b> un pilote clinique. "
        "En cas de danger immédiat, appelez le <b>111</b>, le <b>112</b> ou le <b>115</b>. "
        "(prévention du suicide) est gratuit et joignable 24 h/24 en France.",
        st["warn"],
    ))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Sommaire", st["h1"]))
    toc = [
        "1. À quoi sert l'application et ce qu'elle n'est pas",
        "2. Accéder à la démonstration",
        "3. Créer un compte patient et se connecter",
        "4. Accueil",
        "5. Conversation écrite (cœur du produit)",
        "6. Session vocale",
        "7. Objectifs",
        "8. Check-in PHQ-9",
        "9. Historique",
        "10. Profil et préférences",
        "11. Paramètres, consentements, MFA",
        "12. Espaces clinicien et administration (contrôle d'accès)",
        "13. Sécurité, crise, et ce que l'IA ne décide jamais",
        "14. Résultats des tests du 19 septembre 2026",
        "15. Améliorations proposées",
    ]
    for line in toc:
        story.append(Paragraph(line, st["toc"]))

    story.append(PageBreak())

    # 1
    story.append(Paragraph("1. À quoi sert l'application", st["h1"]))
    story.append(Paragraph(
        "Mensana (nom affiché de Psychologue Intelligent V2) propose un espace confidentiel où une personne "
        "peut écrire ou, si elle l'autorise, parler. Un modèle local génère des réponses de soutien sur le "
        "chemin « vert » (GREEN). Un moteur de crise indépendant du modèle de langage évalue chaque message. "
        "Si le niveau est ORANGE ou ROUGE, l'application n'improvise pas : elle sert des réponses versionnées "
        "et peut ouvrir une alerte pour un clinicien humain.",
        st["body"],
    ))
    story.append(Paragraph("Trois rôles principaux", st["h2"]))
    story.append(table(
        [
            ["Rôle", "Après connexion", "Peut faire"],
            ["Patient", "Accueil, conversation, voix, objectifs, historique, profil, paramètres, check-in",
             "Parler, fixer des objectifs, répondre au PHQ-9, gérer consentements et MFA"],
            ["Clinicien (PSYCHOLOGIST / CLINICAL_SUPERVISOR)", "/clinician",
             "File d'alertes ORANGE/ROUGE, patients suivis, revue de réponses IA, qualité, apprentissage"],
            ["Administrateur (ADMIN)", "/admin",
             "Annuaire, lier un patient à un clinicien, canaux, analytics, gouvernance modèle"],
        ],
        st,
        [38 * mm, 62 * mm, 70 * mm],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Le contrôle d'accès est appliqué <b>côté serveur</b>. Un patient qui ouvre /clinician ou /admin "
        "voit un écran « Accès non autorisé » : ce n'est pas un bug, c'est le comportement attendu.",
        st["body"],
    ))

    # 2
    story.append(Paragraph("2. Accéder à la démonstration", st["h1"]))
    story.append(Paragraph(
        "La démonstration technique V2 est publiée sur Railway. L'interface s'appelle <b>Mensana</b>. "
        "URL web : https://web-production-11e3e.up.railway.app — API : https://api-production-2924.up.railway.app "
        "(santé : /health/live et /health/ready). L'organisation de démo a le slug <b>demo</b> "
        "(placeholder du champ Organisation).",
        st["body"],
    ))
    story.append(Paragraph(
        "Ce n'est pas un hébergement de production clinique : pas de haute disponibilité, pas de canal "
        "de notification réel vers un professionnel de garde, pas de validation clinique du modèle.",
        st["warn"],
    ))

    # 3
    story.append(Paragraph("3. Créer un compte et se connecter", st["h1"]))
    story.append(Paragraph(
        "Ouvrez /login. Deux modes : « Content de vous revoir » (connexion) et « Créer votre espace » (inscription). "
        "Le mot de passe d'inscription exige au moins 12 caractères. Le champ TOTP n'apparaît qu'à la connexion, "
        "si la double authentification a été activée ensuite.",
        st["body"],
    ))
    story.extend(shot("01-login.png", "Figure 1 — Écran de connexion. Organisation = demo.", st))
    story.append(Paragraph("Inscription, étape par étape", st["h2"]))
    story.append(bullets([
        "Cliquer sur « Pas encore de compte ? Créer un compte ».",
        "Saisir le slug d'organisation (demo sur la démonstration).",
        "Saisir un e-mail unique et un mot de passe d'au moins 12 caractères.",
        "Cocher le consentement <b>CARE</b> (suivi thérapeutique). Sans ce consentement, l'API refuse de démarrer une conversation (erreur 403).",
        "Cliquer sur « Créer mon compte ». L'application connecte le compte, enregistre CARE, puis ouvre la conversation.",
    ], st))
    story.extend(shot("02-register.png", "Figure 2 — Inscription avec consentement CARE obligatoire.", st))
    story.append(Paragraph(
        "Si l'API est injoignable, un message « Impossible de contacter le serveur » s'affiche. "
        "Si l'e-mail existe déjà ou le mot de passe est refusé, le message d'erreur API est repris tel quel "
        "(401 → « Identifiants incorrects »).",
        st["body"],
    ))

    # 4
    story.append(Paragraph("4. Accueil", st["h1"]))
    story.append(Paragraph(
        "L'accueil salue selon l'heure (« Bonjour / Bon après-midi / Bonsoir ») et, si renseigné, le nom affiché du profil. "
        "La carte principale mène à la conversation. Deux raccourcis : session vocale et check-in PHQ-9. "
        "Un encart liste les objectifs actifs (ou invite à en créer un).",
        st["body"],
    ))
    story.extend(shot("05-accueil.png", "Figure 3 — Accueil patient connecté.", st))
    story.append(Paragraph(
        "La barre latérale (Accueil, Conversation, Voix, Objectifs, Historique, Alertes, Profil, Paramètres) "
        "reste visible sur tout l'espace patient. Le bouton thème bascule clair/sombre.",
        st["body"],
    ))

    # 5
    story.append(Paragraph("5. Conversation écrite", st["h1"]))
    story.append(Paragraph(
        "C'est le cœur du produit. Au premier accès, un message d'accueil s'affiche : "
        "« Bonjour. Comment vous sentez-vous aujourd'hui ? Je suis là pour vous écouter. » "
        "Le bandeau du bas rappelle l'urgence (111, 112, 115). Ce bandeau n'est pas décoratif : "
        "l'assistant n'est pas un service de crise.",
        st["body"],
    ))
    story.extend(shot("03-conversation.png", "Figure 4 — Conversation vide, avant le premier envoi.", st))
    story.append(Paragraph("Envoyer un message", st["h2"]))
    story.append(bullets([
        "Écrire dans « Écrivez ce que vous ressentez… » (jusqu'à 8 000 caractères côté API).",
        "Cliquer sur Envoyer (ou équivalent clavier selon le navigateur).",
        "Pendant le flux, le champ est désactivé. Le premier tour après un redémarrage du serveur peut durer plusieurs secondes : le modèle GGUF se charge en mémoire CPU.",
        "« Nouvelle conversation » archive le fil courant et en ouvre un autre.",
    ], st))
    story.extend(shot(
        "04-conversation-reponse.png",
        "Figure 5 — Échange réel du 19/09/2026 : le modèle local répond (chemin GREEN), plus le gabarit unique d'autrefois.",
        st,
    ))
    story.append(Paragraph(
        "Limite actuelle visible sur cette capture : le petit modèle (Qwen2.5-0.5B) peut tutoyer, "
        "prendre la voix de l'utilisateur (« tu es toujours là pour me soutenir ») et manquer de clarté clinique. "
        "Cela n'invalide pas le moteur de crise, qui ne passe pas par ce texte. Voir la section 15.",
        st["warn"],
    ))
    story.append(Paragraph(
        "Niveaux de décision (indépendants du LLM) : GREEN = réponse générative de soutien ; "
        "ORANGE / RED = gabarits versionnés + alerte clinicien possible. Un message d'intention suicidaire "
        "ou de plan concret ne doit jamais « discuter » avec le modèle : la politique de crise l'emporte.",
        st["body"],
    ))

    # 6
    story.append(Paragraph("6. Session vocale", st["h1"]))
    story.append(Paragraph(
        "La voix n'est pas un appel WebRTC ni un enregistrement serveur. Le navigateur transcrit (Web Speech) "
        "puis envoie le texte comme un message écrit. La synthèse vocale peut lire la réponse. "
        "Il faut d'abord activer le consentement VOICE (bouton Activer, ou Paramètres → Sessions vocales).",
        st["body"],
    ))
    story.extend(shot("06-voix.png", "Figure 6 — Activation des sessions vocales (transcription locale au navigateur).", st))
    story.append(Paragraph(
        "À prévoir : autoriser le micro dans le navigateur ; un casque réduit les échos ; "
        "l'interrupteur « barge-in » (couper la lecture en parlant) existe dans l'interface une fois la session démarrée. "
        "Ce n'est pas un cabinet téléphonique ni un dispositif d'urgence.",
        st["body"],
    ))

    # 7
    story.append(Paragraph("7. Objectifs", st["h1"]))
    story.append(Paragraph(
        "Les objectifs aident à ancrer le suivi dans le temps (sommeil, activité, relation, etc.). "
        "Ils peuvent influencer le style de l'assistant (le moteur de personnalisation les tisse dans le prompt système).",
        st["body"],
    ))
    story.append(bullets([
        "« + Nouvel objectif » : saisir un titre clair, éventuellement une description.",
        "Marquer la progression au fil des jours.",
        "Un objectif actif apparaît en raccourci sur l'accueil.",
    ], st))
    story.extend(shot("07-objectifs.png", "Figure 7 — Liste d'objectifs vide pour un compte tout juste créé.", st))

    # 8
    story.append(Paragraph("8. Check-in PHQ-9", st["h1"]))
    story.append(Paragraph(
        "Depuis l'accueil, « Check-in rapide » ouvre le questionnaire PHQ-9 (9 items, 0 à 3). "
        "C'est un instrument clinique connu ; ici il sert de <b>point de suivi auto-rapporté</b> dans une démo, "
        "pas de diagnostic délivré par l'application. L'item 9 (pensées de mort / se faire du mal) "
        "déclenche un message d'aide et peut ouvrir une alerte clinicien.",
        st["body"],
    ))
    story.extend(shot("12-checkin.png", "Figure 8 — Check-in PHQ-9. Répondre aux 9 items avant d'envoyer.", st))
    story.append(bullets([
        "Répondre aux 9 questions (Jamais → Presque tous les jours).",
        "« Envoyer mon check-in » n'est actif que lorsque tout est rempli.",
        "Le résultat affiche un score /27 et une bande de sévérité. Ce n'est pas une ordonnance ni un diagnostic.",
        "Si l'item 9 n'est pas à zéro : consigne d'appeler le 111/112/115, indépendamment du modèle de langage.",
    ], st))

    # 9
    story.append(Paragraph("9. Historique", st["h1"]))
    story.append(Paragraph(
        "Toutes les conversations du compte, de la plus récente à la plus ancienne. Un fil « En cours » "
        "peut être rouvert. Le résumé affiché est souvent le dernier message assistant.",
        st["body"],
    ))
    story.extend(shot("08-historique.png", "Figure 9 — Historique après un premier échange.", st))

    # 10
    story.append(Paragraph("10. Profil et préférences", st["h1"]))
    story.append(Paragraph(
        "Le profil n'est visible que par vous (sauf consentements particuliers). "
        "« Modifier » permet de renseigner un nom affiché, un texte « À propos de moi », la langue, "
        "et le <b>style de conversation</b> : ton (chaleureux / neutre / direct), longueur des réponses, "
        "fréquence des questions, directivité. Ces préférences changent le prompt système du chemin GREEN ; "
        "elles ne changent jamais la politique de crise.",
        st["body"],
    ))
    story.extend(shot("10-profil.png", "Figure 10 — Profil : identité et style d'interaction.", st))

    # 11
    story.append(Paragraph("11. Paramètres, consentements, sécurité du compte", st["h1"]))
    story.append(Paragraph(
        "Page dense, à parcourir de haut en bas. Les interrupteurs de consentement sont versionnés et révocables. "
        "Révoquer CARE empêche de poursuivre le suivi conversationnel jusqu'à nouvel accord.",
        st["body"],
    ))
    story.extend(shot("11-parametres.png", "Figure 11 — Paramètres : confidentialité (haut de page).", st))
    story.append(Paragraph("Consentements", st["h2"]))
    story.append(table(
        [
            ["Finalité", "Effet"],
            ["CARE — Suivi thérapeutique", "Obligatoire pour converser."],
            ["LEARNING — Apprentissage continu", "Données anonymisées, revue humaine, pour améliorer le modèle. Désactivé par défaut."],
            ["AI_EXTERNAL — Traitement externe", "Autorise un fournisseur cloud sur le chemin DEEP. Désactivé par défaut ; sans cela, tout reste local."],
            ["VOICE — Sessions vocales", "Transcription navigateur, pas d'audio stocké côté serveur."],
            ["ANALYTICS / RESEARCH", "Stats d'usage ou recherche dé-identifiée. Optionnels."],
        ],
        st,
        [70 * mm, 100 * mm],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Notifications", st["h2"]))
    story.append(Paragraph(
        "Les interrupteurs e-mail / push / SMS / rapport hebdomadaire sont des <b>préférences locales</b>. "
        "La démonstration n'envoie pas encore vers un vrai canal opérationnel (le fournisseur de notif est un journal). "
        "Un rappel de check-in PHQ-9 peut être programmé dans l'interface.",
        st["body"],
    ))
    story.append(Paragraph("Sécurité du compte", st["h2"]))
    story.append(bullets([
        "Configurer la 2FA (TOTP) : enrôlement, puis codes d'application d'authentification à chaque connexion.",
        "Changer le mot de passe (actuel + nouveau + confirmation).",
        "Sessions : révoquer un autre appareil si besoin.",
        "Accessibilité : contraste, texte agrandi, mouvements réduits (stockés dans ce navigateur).",
    ], st))

    # 12
    story.append(Paragraph("12. Clinicien et administration", st["h1"]))
    story.append(Paragraph(
        "Un compte patient n'entre pas dans ces espaces. C'est volontaire : les alertes et l'annuaire "
        "sont des données à accès restreint.",
        st["body"],
    ))
    story.extend(shot("09-alertes.png", "Figure 12 — Lien « Alertes » dans le menu patient : l'API clinicienne refuse l'accès.", st))
    story.extend(shot("13-clinicien.png", "Figure 13 — /clinician avec un compte patient : Accès non autorisé.", st))
    story.extend(shot("14-admin-refuse.png", "Figure 14 — /admin avec un compte patient : même garde-fou.", st))
    story.append(Paragraph("Si vous êtes clinicien (compte provisionné)", st["h2"]))
    story.append(bullets([
        "Connexion avec slug d'organisation, e-mail professionnel, mot de passe, et TOTP si activé. Redirection vers /clinician.",
        "Vue d'ensemble : patients suivis, alertes ROUGES / ORANGE ouvertes, SLA dépassés.",
        "Centre d'alertes : accuser réception, escalader, clôturer — cycle de vie côté serveur.",
        "Patients : dossier de synthèse, historique pertinent, pas un dump brut de tout le fil sans cadre.",
        "Revue IA / qualité / apprentissage : juger des réponses GREEN, jamais pour « corriger » une décision RED déjà figée par la politique.",
    ], st))
    story.append(Paragraph("Si vous êtes administrateur", st["h2"]))
    story.append(bullets([
        "Redirection vers /admin : relations patient–clinicien (créer / clôturer un suivi).",
        "Annuaire des comptes de l'organisation.",
        "Canaux de notification (configuration ; l'envoi réel n'est pas branché en démo).",
        "Analytics (agrégats, pas de réidentification).",
        "Qualité / ML : registre de modèles, promotion — une promotion n'autorise jamais le LLM à classer une crise.",
    ], st))

    # 13
    story.append(Paragraph("13. Sécurité et crise — mode d'emploi « ce qu'il faut savoir »", st["h1"]))
    story.append(Paragraph(
        "L'utilisateur n'a pas à « configurer » le moteur de crise. Il faut en comprendre la logique pour ne pas "
        "surinterpréter l'assistant.",
        st["body"],
    ))
    story.append(bullets([
        "Le classifieur de crise et les règles versionnées s'exécutent avant / à côté du LLM. Le modèle ne vote pas GREEN pour contourner une alerte.",
        "Les tests adversariaux (injection de prompt, extraction du système, contenu dangereux, empoisonnement de contexte) existent dans server/tests/ai_redteam/ — à relancer dès que Redis+Postgres locaux sont disponibles.",
        "L'isolation multi-organisation est testée (un tenant ne lit pas l'autre).",
        "Les secrets ne doivent jamais figurer dans un tutoriel ni un dépôt. Les mots de passe bootstrap Railway ne sont pas reproduits ici.",
        "Le GGUF de production est un petit modèle CPU (Qwen2.5-0.5B). Qualité conversationnelle limitée ; sûreté = politiques, pas « intelligence » du 0.5B.",
    ], st))

    # 14
    story.append(Paragraph("14. Résultats des tests — 19 septembre 2026", st["h1"]))
    story.append(Paragraph(
        "Exécution locale Windows (Python 3.14). Docker Desktop renvoyait une erreur 500 : Redis n'a pas pu démarrer, "
        "donc la suite FastAPI V2 (pytest, y compris red-team) n'a pas été lancée — elle vide volontairement la base "
        "et Redis à chaque test et exige ces services. Ne jamais pointer cette suite vers la base de production.",
        st["body"],
    ))
    story.append(table(
        [
            ["Contrôle", "Résultat", "Commentaire"],
            ["V1 — unittest (tests/)", "122 tests OK", "Crise, notifs en panne simulée, repli LLM : traces d'erreur attendues, suite verte."],
            ["V1 — bandit (backend, scripts)", "0 issue", "Quelques nosec documentés, pas de finding."],
            ["V1 — scan_secrets.py", "Aucun secret", "Propre."],
            ["V1 — ruff", "1 erreur I001", "scripts/benchmark_llm_ttft.py : imports non triés."],
            ["V2 — ruff (server/)", "10 erreurs", "Unions None, noqa inutiles, try/except pass (S110), pathlib en async test."],
            ["V2 — bandit (app, scripts)", "4 findings", "3× B110 (sévérité basse) analytics/goals/mlops ; 1× B310 urlretrieve GGUF (URL épinglée)."],
            ["Frontend — npm audit", "0 vulnérabilité", "info/low/moderate/high/critical = 0."],
            ["pip-audit (interpréteur global)", "Non concluant", "A audité tout le site-packages utilisateur (Django, Tornado, etc.), pas le venv du projet."],
            ["V2 — pytest + ai_redteam", "Non exécuté", "Redis local absent (Docker en échec). Postgres 5432 était ouvert, insuffisant seul."],
            ["Parcours UI démo", "OK", "Inscription CARE, conversation générative, pages patient, 403 clinicien/admin."],
        ],
        st,
        [48 * mm, 38 * mm, 84 * mm],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Interprétation honnête : la fondation V1 et le parcours patient V2 déployé tiennent. "
        "La porte qualité V2 « comme en CI » (pytest + coverage 85 % + red-team + pip-audit isolé) "
        "n'est pas rejouée ici faute d'environnement Docker. C'est un écart d'outillage local, pas une preuve d'absence de tests dans le dépôt.",
        st["body"],
    ))

    # 15
    story.append(Paragraph("15. Améliorations proposées", st["h1"]))
    story.append(Paragraph("Produit et conversation", st["h2"]))
    story.append(bullets([
        "<b>Prompt système plus strict pour le 0.5B</b> : vouvoiement, ne jamais parler à la place de l'utilisateur, une question max, interdiction des conseils médicaux. Le 0.5B actuel inverse parfois les rôles.",
        "<b>Warm-up du GGUF</b> au démarrage (requête interne) pour éviter un premier message très lent, avec timeout et repli gabarit explicite dans l'UI (« l'assistant démarre… »).",
        "<b>Afficher le chemin</b> (GREEN génératif vs gabarit de crise) d'une façon non anxiogène pour le patient, et clairement pour le clinicien.",
        "<b>Masquer « Alertes »</b> dans la navigation patient : l'écran actuel dit que c'est réservé aux cliniciens — le lien ne devrait pas s'y trouver.",
        "<b>Qualité modèle</b> : passer à 1.5B/3B dès qu'un GPU ou plus de RAM CPU est disponible ; garder le 0.5B comme repli, pas comme voix « produit ».",
    ], st))
    story.append(Paragraph("Sûreté et clinique", st["h2"]))
    story.append(bullets([
        "Ne jamais présenter le PHQ-9 auto-administré comme un diagnostic. Clarifier la bande de sévérité (« indicateur, à relire avec un clinicien »).",
        "Brancher un vrai canal d'alerte (astreinte) avant tout pilote : aujourd'hui les notifications sont essentiellement journalisées.",
        "Procédure de perte de secret TOTP (ré-enrôlement supervisé) : aujourd'hui une perte impose souvent de recréer le compte.",
        "Étude clinique / protocole : hors scope actuel ; ne pas le contourner par du marketing « psychologue intelligent ».",
    ], st))
    story.append(Paragraph("Ingénierie et sécurité", st["h2"]))
    story.append(bullets([
        "Remettre Docker Desktop (ou un Redis Windows/WSL) pour rejouer pytest V2 + coverage + -m ai_redteam en local.",
        "pip-audit et bandit dans un venv projet, jamais sur le Python utilisateur global.",
        "Corriger les 10 ruff V2 et remplacer les except/pass (B110) par un log structuré.",
        "Mémoire Railway : dimensionner l'API pour GGUF mmap + uvicorn (risque d'OOM → retour silencieux aux gabarits).",
        "Healthcheck / timeout du premier chargement modèle ; métrique TTFT déjà prévue (analytics).",
        "Ne pas fusionner feat/v2 vers main tant que la voix WebRTC, les tests de charge et le readiness clinique ne sont pas tranchés — et ne pas le prétendre fait.",
    ], st))

    story.append(Paragraph("Aide-mémoire utilisateur", st["h1"]))
    story.append(table(
        [
            ["Je veux…", "J'ouvre…"],
            ["Parler par écrit", "Conversation"],
            ["Parler à voix haute", "Voix (consentement VOICE + micro)"],
            ["Faire le point sur 2 semaines", "Accueil → Check-in rapide (PHQ-9)"],
            ["Me fixer un but", "Objectifs"],
            ["Retrouver un vieux fil", "Historique"],
            ["Changer le ton de l'assistant", "Profil → Style de conversation"],
            ["Retirer un consentement / activer la 2FA", "Paramètres"],
            ["Une urgence vitale", "111, 112, 115 — pas l'assistant"],
        ],
        st,
        [80 * mm, 90 * mm],
    ))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Document généré le 19 septembre 2026 à partir de l'application déployée et du code du dépôt. "
        "Les captures montrent un compte patient de démonstration. Aucun mot de passe, clé JWT ni secret TOTP n'y figure.",
        st["small"],
    ))

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        title="Mensana — tutoriel d'utilisation complet",
        author="Documentation projet Psychologue Intelligent",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
