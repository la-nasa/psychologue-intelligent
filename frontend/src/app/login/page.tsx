"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ApiError, grantConsent, login, register } from "@/lib/api"

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
          // dès son premier message, sans indication de quoi faire. Inscription
          // -> connexion -> octroi CARE -> conversation, en une seule action
          // explicite (la case à cocher nomme le consentement).
          await login(organizationSlug, email, password)
          await grantConsent("CARE")
          router.push("/conversation")
        } catch {
          // Le compte existe malgré l'échec de cette suite — ne pas le cacher.
          setRegistered(true)
          setMode("login")
        }
      } else {
        await login(organizationSlug, email, password, totpCode || undefined)
        router.push("/conversation")
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Identifiants incorrects." : err.message)
      } else {
        setError("Impossible de contacter le serveur. Vérifiez qu'il est démarré.")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{mode === "login" ? "Connexion" : "Créer un compte"}</CardTitle>
          <CardDescription>
            {mode === "login"
              ? "Connectez-vous pour accéder à vos conversations."
              : "Inscription patient — un clinicien vous rattachera ensuite."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="org">Organisation</Label>
              <Input
                id="org"
                placeholder="demo"
                value={organizationSlug}
                onChange={(e) => setOrganizationSlug(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">E-mail</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
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
              <div className="space-y-2">
                <Label htmlFor="totp">Code MFA (si activé)</Label>
                <Input
                  id="totp"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  placeholder="optionnel"
                />
              </div>
            )}
            {mode === "register" && (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={careConsent}
                  onChange={(e) => setCareConsent(e.target.checked)}
                  required
                />
                <span>
                  J&apos;accepte le suivi thérapeutique (consentement <strong>CARE</strong>), nécessaire pour
                  utiliser l&apos;assistant. Révocable à tout moment dans Paramètres.
                </span>
              </label>
            )}

            {registered && mode === "login" && (
              <p className="text-sm text-emerald-600">Compte créé, vous pouvez vous connecter.</p>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "..." : mode === "login" ? "Se connecter" : "Créer mon compte"}
            </Button>
          </form>

          <button
            type="button"
            className="mt-4 w-full text-center text-sm text-muted-foreground hover:underline"
            onClick={() => {
              setError(null)
              setMode(mode === "login" ? "register" : "login")
            }}
          >
            {mode === "login" ? "Pas de compte ? Créer un compte patient" : "Déjà un compte ? Se connecter"}
          </button>
        </CardContent>
      </Card>
    </div>
  )
}
