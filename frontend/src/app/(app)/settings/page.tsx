"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { KeyRound, Fingerprint, MonitorSmartphone, Check, Laptop, X, CalendarClock } from "lucide-react"
import {
  ApiError,
  activateMfa,
  changePassword,
  clearToken,
  ConsentItem,
  ConsentPurpose,
  enrollMfa,
  getToken,
  grantConsent,
  listConsents,
  listReminders,
  listSessions,
  ReminderItem,
  revokeConsent,
  revokeSession,
  scheduleReminder,
  SessionItem,
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

function PasswordSection({ onChanged }: { onChanged: () => void }) {
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(false)
    if (next.length < 12) {
      setError("Le nouveau mot de passe doit contenir au moins 12 caractères.")
      return
    }
    if (next !== confirm) {
      setError("La confirmation ne correspond pas au nouveau mot de passe.")
      return
    }
    setBusy(true)
    try {
      await changePassword(current, next)
      setCurrent("")
      setNext("")
      setConfirm("")
      setSuccess(true)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Mot de passe actuel incorrect." : "Impossible de changer le mot de passe.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 py-3.5">
      <div className="flex items-center gap-3 text-sm font-medium">
        <KeyRound className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
        Changer le mot de passe
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <Input
          type="password"
          placeholder="Mot de passe actuel"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Input
          type="password"
          placeholder="Nouveau mot de passe"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          minLength={12}
          autoComplete="new-password"
          required
        />
        <Input
          type="password"
          placeholder="Confirmer"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          minLength={12}
          autoComplete="new-password"
          required
        />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && (
        <p className="flex items-center gap-2 text-sm text-success">
          <Check className="h-4 w-4" strokeWidth={1.75} /> Mot de passe mis à jour. Vos autres sessions ont été déconnectées.
        </p>
      )}
      <Button type="submit" size="sm" variant="outline" disabled={busy || !current || !next || !confirm}>
        {busy ? "Un instant…" : "Mettre à jour"}
      </Button>
    </form>
  )
}

function SessionsSection({ refreshKey }: { refreshKey: number }) {
  const [sessions, setSessions] = useState<SessionItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revokingId, setRevokingId] = useState<string | null>(null)

  const refresh = () => {
    listSessions()
      .then(setSessions)
      .catch(() => setError("Impossible de charger les sessions actives."))
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  const handleRevoke = async (id: string) => {
    setRevokingId(id)
    try {
      await revokeSession(id)
      refresh()
    } catch {
      setError("Impossible de révoquer cette session.")
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <div className="space-y-2 py-3.5">
      <div className="flex items-center gap-3 text-sm font-medium">
        <MonitorSmartphone className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
        Sessions actives
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {sessions && (
        <div className="divide-y rounded-md border">
          {sessions.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
              <div className="flex items-center gap-2.5">
                <Laptop className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
                <div>
                  <p className="font-medium">
                    {s.current ? "Cette session" : "Autre session"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Ouverte le {new Date(s.created_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}
                  </p>
                </div>
              </div>
              {s.current ? (
                <span className="text-xs text-muted-foreground">Appareil actuel</span>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  disabled={revokingId === s.id}
                  onClick={() => handleRevoke(s.id)}
                >
                  <X className="h-3.5 w-3.5" strokeWidth={1.75} /> Révoquer
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const REMINDER_STATUS_LABELS: Record<ReminderItem["status"], string> = {
  PENDING: "À venir",
  SENT: "Envoyé",
  DONE: "Terminé",
  CANCELLED: "Annulé",
}

function ReminderSection() {
  const [reminders, setReminders] = useState<ReminderItem[] | null>(null)
  const [dueAt, setDueAt] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = () => {
    listReminders()
      .then(setReminders)
      .catch(() => setError("Impossible de charger vos rappels."))
  }

  useEffect(() => {
    refresh()
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dueAt) return
    setError(null)
    setBusy(true)
    try {
      await scheduleReminder(new Date(dueAt).toISOString())
      setDueAt("")
      refresh()
    } catch {
      setError("Impossible de programmer ce rappel — choisissez une date future.")
    } finally {
      setBusy(false)
    }
  }

  const upcoming = reminders?.filter((r) => r.status === "PENDING") ?? []

  return (
    <div className="space-y-3 py-3.5">
      <div className="space-y-0.5">
        <Label className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
          Rappel de check-in
        </Label>
        <p className="text-sm text-muted-foreground">Programmez une relance pour votre prochain point PHQ-9.</p>
      </div>
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <Input
          type="datetime-local"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          className="w-auto"
        />
        <Button type="submit" size="sm" variant="outline" disabled={busy || !dueAt}>
          {busy ? "Un instant…" : "Programmer"}
        </Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {upcoming.length > 0 && (
        <ul className="space-y-1 text-sm text-muted-foreground">
          {upcoming.map((r) => (
            <li key={r.id} className="flex items-center justify-between">
              <span>{new Date(r.due_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}</span>
              <span className="text-xs">{REMINDER_STATUS_LABELS[r.status]}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function SettingsPage() {
  const [notifications, setNotifications] = useState({
    email: true,
    push: true,
    sms: false,
    weeklyReport: true,
  })

  const [accessibility, setAccessibility] = useState({
    highContrast: false,
    largeText: false,
    reducedMotion: false,
  })

  const [sessionsRefreshKey, setSessionsRefreshKey] = useState(0)

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
            label="Rapport hebdomadaire"
            description="Résumé de votre progression chaque semaine."
            checked={notifications.weeklyReport}
            onCheckedChange={(v) => setNotifications({ ...notifications, weeklyReport: v })}
          />
          <ReminderSection />
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
          <PasswordSection onChanged={() => setSessionsRefreshKey((k) => k + 1)} />
          <SessionsSection refreshKey={sessionsRefreshKey} />
        </CardContent>
      </Card>
    </div>
  )
}
