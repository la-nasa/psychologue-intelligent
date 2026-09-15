"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, getMe, grantConsent, landingPathForRoles, login, register } from "@/lib/api"

type Mode = "login" | "register"

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>("login")
  const [organizationSlug, setOrganizationSlug] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [totpCode, setTotpCode] = useState("")
  const [careConsent, setCareConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [registered, setRegistered] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (mode === "register") {
        await register(organizationSlug, email, password)
        try {
          // L'API de démarrage de conversation exige un consentement CARE actif
          // (server/app/application/conversation.py) — sans cette étape, un
          // patient fraîchement inscrit se heurtait à un 403 incompréhensible
          // dès son premier message. Inscription -> connexion -> octroi CARE
          // -> conversation, en une seule action explicite.
          await login(organizationSlug, email, password)
          await grantConsent("CARE")
          router.push("/conversation")
        } catch {
          setRegistered(true)
          setMode("login")
        }
      } else {
        await login(organizationSlug, email, password, totpCode || undefined)
        const me = await getMe()
        router.push(landingPathForRoles(me.roles))
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Identifiants incorrects." : err.message)
      } else {
        setError("Impossible de contacter le serveur. Réessayez dans un instant.")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <span className="h-2 w-2 rounded-full bg-primary" aria-hidden />
          <h1 className="text-xl font-semibold tracking-tight">Mensana</h1>
          <p className="text-sm text-muted-foreground">Un espace pour parler, en toute confiance.</p>
        </div>

        <div className="rounded-xl border bg-card p-6 shadow-soft-lg">
          <div className="mb-5 space-y-1">
            <h2 className="text-lg font-medium tracking-tight">
              {mode === "login" ? "Content de vous revoir" : "Créer votre espace"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {mode === "login"
                ? "Connectez-vous pour retrouver vos conversations."
                : "Un clinicien pourra vous suivre une fois votre compte créé."}
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-1.5">
              <Label htmlFor="org">Organisation</Label>
              <Input id="org" placeholder="demo" value={organizationSlug} onChange={(e) => setOrganizationSlug(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Mot de passe</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={mode === "register" ? 12 : undefined}
                required
              />
            </div>
            {mode === "login" && (
              <div className="space-y-1.5">
                <Label htmlFor="totp">Code d&apos;authentification (si activé)</Label>
                <Input id="totp" value={totpCode} onChange={(e) => setTotpCode(e.target.value)} placeholder="Optionnel" />
              </div>
            )}
            {mode === "register" && (
              <label className="flex items-start gap-2.5 rounded-md border bg-muted/40 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                  checked={careConsent}
                  onChange={(e) => setCareConsent(e.target.checked)}
                  required
                />
                <span className="text-foreground/80">
                  J&apos;accepte le suivi thérapeutique (consentement <strong className="font-medium">CARE</strong>),
                  nécessaire pour utiliser l&apos;assistant. Révocable à tout moment.
                </span>
              </label>
            )}

            {registered && mode === "login" && (
              <p className="rounded-md border border-success/20 bg-success/10 px-3 py-2 text-sm text-success">
                Compte créé — vous pouvez vous connecter.
              </p>
            )}
            {error && (
              <p className="rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Un instant…" : mode === "login" ? "Se connecter" : "Créer mon compte"}
            </Button>
          </form>

          <button
            type="button"
            className="mt-5 w-full text-center text-sm text-muted-foreground hover:text-foreground"
            onClick={() => {
              setError(null)
              setMode(mode === "login" ? "register" : "login")
            }}
          >
            {mode === "login" ? (
              <>Pas encore de compte ? <span className="font-medium text-primary">Créer un compte</span></>
            ) : (
              <>Déjà un compte ? <span className="font-medium text-primary">Se connecter</span></>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
