"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Bell, Shield, Eye, Volume2, Globe, Key } from "lucide-react"
import { ApiError, clearToken, ConsentItem, ConsentPurpose, getToken, grantConsent, listConsents, revokeConsent } from "@/lib/api"

const CONSENT_LABELS: Record<ConsentPurpose, { label: string; description: string }> = {
  CARE: { label: "Suivi thérapeutique (CARE)", description: "Nécessaire pour utiliser l'assistant et le suivi clinique." },
  LEARNING: { label: "Apprentissage continu", description: "Autoriser l'utilisation anonymisée et revue par un clinicien pour améliorer le modèle." },
  AI_EXTERNAL: { label: "IA externe (cloud)", description: "Autoriser l'envoi de messages complexes à un fournisseur externe (Anthropic/OpenAI) plutôt qu'au modèle local uniquement." },
  VOICE: { label: "Sessions vocales", description: "Autoriser l'enregistrement et le traitement de votre voix (fonctionnalité pas encore disponible)." },
  ANALYTICS: { label: "Analyses anonymes", description: "Contribuer aux statistiques d'usage anonymisées du produit." },
  RESEARCH: { label: "Recherche", description: "Autoriser l'utilisation de données dé-identifiées à des fins de recherche." },
}

function ConsentSection() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [consents, setConsents] = useState<ConsentItem[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = () => {
    listConsents()
      .then(setConsents)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          setAuthed(false)
        } else {
          setError("Impossible de charger les consentements.")
        }
      })
  }

  useEffect(() => {
    if (!getToken()) {
      setAuthed(false)
      return
    }
    setAuthed(true)
    refresh()
  }, [])

  const toggle = async (purpose: ConsentPurpose, active: boolean) => {
    try {
      if (active) await revokeConsent(purpose)
      else await grantConsent(purpose)
      refresh()
    } catch {
      setError("Impossible de mettre à jour ce consentement.")
    }
  }

  if (authed === false) {
    return (
      <p className="text-sm text-muted-foreground">
        <Link href="/login" className="underline">
          Connectez-vous
        </Link>{" "}
        pour gérer vos consentements.
      </p>
    )
  }

  const isActive = (purpose: ConsentPurpose) => consents.find((c) => c.purpose === purpose)?.active ?? false

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      {(Object.keys(CONSENT_LABELS) as ConsentPurpose[]).map((purpose, i) => (
        <div key={purpose}>
          {i > 0 && <Separator className="mb-4" />}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{CONSENT_LABELS[purpose].label}</Label>
              <p className="text-sm text-muted-foreground">{CONSENT_LABELS[purpose].description}</p>
            </div>
            <Switch checked={isActive(purpose)} onCheckedChange={() => toggle(purpose, isActive(purpose))} />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function SettingsPage() {
  const [notifications, setNotifications] = useState({
    email: true,
    push: true,
    sms: false,
    dailyReminder: true,
    weeklyReport: true,
    alertNotifications: true,
  })

  const [accessibility, setAccessibility] = useState({
    highContrast: false,
    largeText: false,
    screenReader: false,
    reducedMotion: false,
  })

  const [voice, setVoice] = useState({
    autoPlayResponses: true,
    voiceSpeed: 1.0,
    voiceVolume: 0.8,
    noiseCancellation: true,
  })

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Paramètres</h2>
          <p className="text-muted-foreground">
            Personnalisez votre expérience et gérez vos préférences
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 space-y-6 p-6">
        {/* Notifications */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-primary" />
              <CardTitle>Notifications</CardTitle>
            </div>
            <CardDescription>
              Préférences locales à ce navigateur — pas encore reliées au service de notifications réel
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Email</Label>
                <p className="text-sm text-muted-foreground">
                  Recevoir des notifications par email
                </p>
              </div>
              <Switch
                checked={notifications.email}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, email: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Push</Label>
                <p className="text-sm text-muted-foreground">
                  Notifications push sur votre appareil
                </p>
              </div>
              <Switch
                checked={notifications.push}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, push: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>SMS</Label>
                <p className="text-sm text-muted-foreground">
                  Alertes importantes par SMS
                </p>
              </div>
              <Switch
                checked={notifications.sms}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, sms: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Rappel quotidien</Label>
                <p className="text-sm text-muted-foreground">
                  Rappel pour votre check-in quotidien
                </p>
              </div>
              <Switch
                checked={notifications.dailyReminder}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, dailyReminder: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Rapport hebdomadaire</Label>
                <p className="text-sm text-muted-foreground">
                  Résumé de votre progression chaque semaine
                </p>
              </div>
              <Switch
                checked={notifications.weeklyReport}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, weeklyReport: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Privacy — branché sur le vrai système de consentement (server/app/api/account.py) */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <CardTitle>Confidentialité</CardTitle>
            </div>
            <CardDescription>Consentements par finalité, versionnés et révocables à tout moment</CardDescription>
          </CardHeader>
          <CardContent>
            <ConsentSection />
          </CardContent>
        </Card>

        {/* Accessibility — préférences locales uniquement, pas encore de backend dédié */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-primary" />
              <CardTitle>Accessibilité</CardTitle>
            </div>
            <CardDescription>
              Améliorez l&apos;accessibilité de l&apos;interface (préférences locales à ce navigateur pour l&apos;instant)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Contraste élevé</Label>
                <p className="text-sm text-muted-foreground">
                  Augmente le contraste des éléments
                </p>
              </div>
              <Switch
                checked={accessibility.highContrast}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, highContrast: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Texte agrandi</Label>
                <p className="text-sm text-muted-foreground">
                  Taille de police plus grande
                </p>
              </div>
              <Switch
                checked={accessibility.largeText}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, largeText: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Lecteur d&apos;écran</Label>
                <p className="text-sm text-muted-foreground">
                  Optimisé pour les lecteurs d&apos;écran
                </p>
              </div>
              <Switch
                checked={accessibility.screenReader}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, screenReader: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Mouvements réduits</Label>
                <p className="text-sm text-muted-foreground">
                  Diminue les animations
                </p>
              </div>
              <Switch
                checked={accessibility.reducedMotion}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, reducedMotion: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Voice */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Volume2 className="h-5 w-5 text-primary" />
              <CardTitle>Vocal</CardTitle>
            </div>
            <CardDescription>
              Paramètres des sessions vocales — le moteur vocal lui-même n&apos;est pas encore implémenté (Phase 11)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Lecture automatique</Label>
                <p className="text-sm text-muted-foreground">
                  Lire automatiquement les réponses de l&apos;IA
                </p>
              </div>
              <Switch
                checked={voice.autoPlayResponses}
                onCheckedChange={(checked) =>
                  setVoice({ ...voice, autoPlayResponses: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Réduction du bruit</Label>
                <p className="text-sm text-muted-foreground">
                  Filtrer les bruits de fond pendant les appels
                </p>
              </div>
              <Switch
                checked={voice.noiseCancellation}
                onCheckedChange={(checked) =>
                  setVoice({ ...voice, noiseCancellation: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Security */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-primary" />
              <CardTitle>Sécurité</CardTitle>
            </div>
            <CardDescription>Ces actions existent côté API mais n&apos;ont pas encore d&apos;écran dédié ici</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" className="w-full justify-start" disabled>
              <Key className="mr-2 h-4 w-4" />
              Changer le mot de passe (à venir)
            </Button>
            <Button variant="outline" className="w-full justify-start" disabled>
              <Shield className="mr-2 h-4 w-4" />
              Activer l&apos;authentification à deux facteurs (API prête : /auth/mfa/enroll — écran à venir)
            </Button>
            <Button variant="outline" className="w-full justify-start" disabled>
              <Globe className="mr-2 h-4 w-4" />
              Gérer les sessions actives (à venir)
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
