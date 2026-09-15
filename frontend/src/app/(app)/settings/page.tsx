"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { KeyRound, ShieldCheck, Fingerprint, MonitorSmartphone, Check } from "lucide-react"
import {
  ApiError,
  activateMfa,
  clearToken,
  ConsentItem,
  ConsentPurpose,
  enrollMfa,
  getToken,
  grantConsent,
  listConsents,
  revokeConsent,
} from "@/lib/api"

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

type MfaState = "idle" | "enrolling" | "pending_activation" | "active"

function MfaSection() {
  const [state, setState] = useState<MfaState>("idle")
  const [secret, setSecret] = useState("")
  const [otpauthUri, setOtpauthUri] = useState("")
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const startEnrollment = async () => {
    setError(null)
    setBusy(true)
    try {
      const res = await enrollMfa()
      setSecret(res.secret)
      setOtpauthUri(res.otpauth_uri)
      setState("pending_activation")
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setState("active")
      } else {
        setError("Impossible de démarrer la configuration.")
      }
    } finally {
      setBusy(false)
    }
  }

  const activate = async () => {
    setError(null)
    setBusy(true)
    try {
      await activateMfa(code)
      setState("active")
    } catch {
      setError("Code invalide. Vérifiez votre application d'authentification.")
    } finally {
      setBusy(false)
    }
  }

  if (state === "active") {
    return (
      <p className="flex items-center gap-2 py-2.5 text-sm text-success">
        <Check className="h-4 w-4" strokeWidth={1.75} /> Authentification à deux facteurs activée.
      </p>
    )
  }

  if (state === "pending_activation") {
    return (
      <div className="space-y-3 rounded-md border p-4">
        <p className="text-sm">
          Ajoutez ce compte dans votre application d&apos;authentification (Google Authenticator, 1Password…), avec la
          clé secrète ci-dessous, puis saisissez le code à 6 chiffres généré.
        </p>
        <div className="space-y-1">
          <p className="break-all rounded-md bg-muted/50 px-3 py-2 font-mono text-xs">{secret}</p>
          <p className="break-all text-xs text-muted-foreground">{otpauthUri}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Code à 6 chiffres"
            className="w-40"
            maxLength={10}
          />
          <Button size="sm" onClick={activate} disabled={busy || code.length < 6}>
            {busy ? "Vérification…" : "Activer"}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-2 py-2.5">
      <Button size="sm" variant="outline" onClick={startEnrollment} disabled={busy}>
        {busy ? "Un instant…" : "Configurer la 2FA"}
      </Button>
      {error && <p className="text-sm text-destructive">{error}</p>}
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
          <CardDescription>Protégez l&apos;accès à votre compte.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          <div className="space-y-1 py-2.5">
            <div className="flex items-center gap-3 text-sm font-medium">
              <Fingerprint className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
              Authentification à deux facteurs
            </div>
            <MfaSection />
          </div>
          {[
            { icon: KeyRound, label: "Changer le mot de passe" },
            { icon: MonitorSmartphone, label: "Sessions actives" },
          ].map(({ icon: Icon, label }) => (
            <div key={label} className="flex items-center gap-3 px-1 py-2.5 text-sm text-muted-foreground">
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
