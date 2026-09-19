"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, getMe, grantConsent, landingPathForRoles, login, register } from "@/lib/api"
import { EMERGENCY_NUMBERS } from "@/lib/emergency"

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
    <main className="grid min-h-[100dvh] overflow-x-hidden lg:grid-cols-[1.1fr_0.9fr]">
      <section className="relative hidden flex-col justify-between bg-[#345A63] px-12 py-12 text-[#F7F4EE] lg:flex">
        <div className="flex items-baseline gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[#F7F4EE]" aria-hidden />
          <span className="text-sm font-semibold tracking-tight">Mensana</span>
        </div>
        <div className="max-w-md space-y-5">
          <h1 className="max-w-xl text-[clamp(2rem,3.4vw,3.25rem)] font-semibold leading-[1.12] tracking-tight">
            Un espace pour parler, à votre rythme.
          </h1>
          <p className="max-w-[42ch] text-sm leading-relaxed text-[#F7F4EE]/75">
            Soutien conversationnel confidentiel. Ce n&apos;est pas un psychologue, ni un service d&apos;urgence.
          </p>
        </div>
        <p className="text-xs text-[#F7F4EE]/60">
          En danger immédiat : {EMERGENCY_NUMBERS}
        </p>
      </section>

      <section className="flex min-h-[100dvh] flex-col justify-center px-5 py-12 sm:px-10">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 space-y-2 lg:hidden">
            <div className="flex items-baseline gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
              <span className="text-sm font-semibold tracking-tight">Mensana</span>
            </div>
            <p className="text-sm text-muted-foreground">Un espace pour parler, en toute confiance.</p>
          </div>

          <div className="space-y-1.5">
            <h2 className="text-2xl font-semibold tracking-tight">
              {mode === "login" ? "Content de vous revoir" : "Créer votre espace"}
            </h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {mode === "login"
                ? "Connectez-vous pour retrouver vos conversations."
                : "Un clinicien pourra vous suivre une fois votre compte créé."}
            </p>
          </div>

          <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-2">
              <Label htmlFor="org">Organisation</Label>
              <Input
                id="org"
                placeholder="demo"
                value={organizationSlug}
                onChange={(e) => setOrganizationSlug(e.target.value)}
                required
                autoComplete="organization"
              />
              <p className="text-xs text-muted-foreground">Identifiant fourni par votre établissement.</p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Mot de passe</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={mode === "register" ? 12 : undefined}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>
            {mode === "login" && (
              <div className="grid gap-2">
                <Label htmlFor="totp">Code d&apos;authentification</Label>
                <Input id="totp" value={totpCode} onChange={(e) => setTotpCode(e.target.value)} placeholder="Si la 2FA est activée" />
              </div>
            )}
            {mode === "register" && (
              <label className="flex items-start gap-2.5 rounded-xl border bg-muted/40 p-3 text-sm">
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
              <p className="rounded-xl border border-success/20 bg-success/10 px-3 py-2 text-sm text-success">
                Compte créé — vous pouvez vous connecter.
              </p>
            )}
            {error && (
              <p className="rounded-xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <Button type="submit" className="h-11 w-full" disabled={submitting}>
              {submitting ? "Un instant…" : mode === "login" ? "Se connecter" : "Créer mon compte"}
            </Button>
          </form>

          <button
            type="button"
            className="mt-6 w-full text-center text-sm text-muted-foreground hover:text-foreground"
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
      </section>
    </main>
  )
}
