"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { KeyRound, ShieldCheck, Fingerprint, MonitorSmartphone } from "lucide-react"
import { ApiError, clearToken, ConsentItem, ConsentPurpose, getToken, grantConsent, listConsents, revokeConsent } from "@/lib/api"

const CONSENT_LABELS: Record<ConsentPurpose, { label: string; description: string }> = {
  CARE: { label: "Suivi thérapeutique", description: "Nécessaire pour utiliser l'assistant et le suivi clinique." },
  LEARNING: { label: "Apprentissage continu", description: "Utilisation anonymisée et revue par un clinicien, pour améliorer le modèle." },
  AI_EXTERNAL: { label: "Traitement externe", description: "Autoriser l'envoi de messages complexes à un fournisseur cloud plutôt qu'au modèle local uniquement." },
  VOICE: { label: "Sessions vocales", description: "Enregistrement et traitement de la voix — fonctionnalité pas encore disponible." },
  ANALYTICS: { label: "Analyses anonymes", description: "Contribuer aux statistiques d'usage anonymisées du produit." },
  RESEARCH: { label: "Recherche", description: "Utilisation de données dé-identifiées à des fins de recherche." },
}

function SettingsRow({
  label,
  description,
  checked,
  onCheckedChange,
}: {
  label: string
  description: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3.5">
      <div className="space-y-0.5">
        <Label>{label}</Label>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  )
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
        <Link href="/login" className="font-medium text-primary underline-offset-4 hover:underline">
          Connectez-vous
        </Link>{" "}
        pour gérer vos consentements.
      </p>
    )
  }

  const isActive = (purpose: ConsentPurpose) => consents.find((c) => c.purpose === purpose)?.active ?? false

  return (
    <div className="divide-y">
      {error && <p className="pb-3 text-sm text-destructive">{error}</p>}
      {(Object.keys(CONSENT_LABELS) as ConsentPurpose[]).map((purpose) => (
        <SettingsRow
          key={purpose}
          label={CONSENT_LABELS[purpose].label}
          description={CONSENT_LABELS[purpose].description}
          checked={isActive(purpose)}
          onCheckedChange={() => toggle(purpose, isActive(purpose))}
        />
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
  })

  const [accessibility, setAccessibility] = useState({
    highContrast: false,
    largeText: false,
    reducedMotion: false,
  })

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Paramètres</h1>
        <p className="text-sm text-muted-foreground">Personnalisez votre expérience et gérez vos données.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Confidentialité</CardTitle>
          <CardDescription>Consentements par finalité, versionnés et révocables à tout moment.</CardDescription>
        </CardHeader>
        <CardContent>
          <ConsentSection />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
          <CardDescription>Préférences locales — pas encore reliées au service d&apos;envoi réel.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          <SettingsRow
            label="E-mail"
            description="Recevoir des notifications par e-mail."
            checked={notifications.email}
            onCheckedChange={(v) => setNotifications({ ...notifications, email: v })}
          />
          <SettingsRow
            label="Notifications push"
            description="Sur cet appareil."
            checked={notifications.push}
            onCheckedChange={(v) => setNotifications({ ...notifications, push: v })}
          />
          <SettingsRow
            label="SMS"
            description="Pour les alertes importantes uniquement."
            checked={notifications.sms}
            onCheckedChange={(v) => setNotifications({ ...notifications, sms: v })}
          />
          <SettingsRow
            label="Rappel quotidien"
            description="Un rappel pour votre point du jour."
            checked={notifications.dailyReminder}
            onCheckedChange={(v) => setNotifications({ ...notifications, dailyReminder: v })}
          />
          <SettingsRow
            label="Rapport hebdomadaire"
            description="Résumé de votre progression chaque semaine."
            checked={notifications.weeklyReport}
            onCheckedChange={(v) => setNotifications({ ...notifications, weeklyReport: v })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Accessibilité</CardTitle>
          <CardDescription>Préférences locales à ce navigateur.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          <SettingsRow
            label="Contraste élevé"
            description="Augmente le contraste des éléments."
            checked={accessibility.highContrast}
            onCheckedChange={(v) => setAccessibility({ ...accessibility, highContrast: v })}
          />
          <SettingsRow
            label="Texte agrandi"
            description="Taille de police plus grande."
            checked={accessibility.largeText}
            onCheckedChange={(v) => setAccessibility({ ...accessibility, largeText: v })}
          />
          <SettingsRow
            label="Mouvements réduits"
            description="Diminue les animations de l'interface."
            checked={accessibility.reducedMotion}
            onCheckedChange={(v) => setAccessibility({ ...accessibility, reducedMotion: v })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sécurité</CardTitle>
          <CardDescription>Disponible via l&apos;API ; l&apos;écran dédié arrive prochainement.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1">
          {[
            { icon: KeyRound, label: "Changer le mot de passe" },
            { icon: Fingerprint, label: "Authentification à deux facteurs" },
            { icon: MonitorSmartphone, label: "Sessions actives" },
          ].map(({ icon: Icon, label }) => (
            <div key={label} className="flex items-center gap-3 rounded-md px-1 py-2.5 text-sm text-muted-foreground">
              <Icon className="h-4 w-4" strokeWidth={1.75} />
              {label}
              <span className="ml-auto flex items-center gap-1 text-xs">
                <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.75} />
                bientôt
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
