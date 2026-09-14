"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Textarea } from "@/components/ui/textarea"
import { Pencil, Check, X } from "lucide-react"
import {
  ApiError,
  clearToken,
  getPreferences,
  getProfile,
  getToken,
  Preferences,
  ProfileData,
  requestAccountDeletion,
  savePreferences,
  saveProfile,
} from "@/lib/api"

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm transition-colors hover:border-foreground/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"

export default function ProfilePage() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleteRequested, setDeleteRequested] = useState(false)

  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  const [draft, setDraft] = useState({ displayName: "", aboutMe: "", language: "fr" as "fr" | "en" })

  useEffect(() => {
    if (!getToken()) {
      setAuthed(false)
      return
    }
    setAuthed(true)
    Promise.all([getProfile(), getPreferences()])
      .then(([p, pr]) => {
        setProfile(p)
        setPrefs(pr)
        setDraft({ displayName: p.display_name, aboutMe: p.about_me, language: p.language })
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          setAuthed(false)
        } else {
          setError("Impossible de charger le profil.")
        }
      })
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    try {
      await saveProfile(draft.displayName, draft.aboutMe, draft.language)
      setProfile((p) => (p ? { ...p, display_name: draft.displayName, about_me: draft.aboutMe, language: draft.language } : p))
      setIsEditing(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch {
      setError("Impossible d'enregistrer le profil.")
    }
  }

  const handleCancel = () => {
    if (profile) setDraft({ displayName: profile.display_name, aboutMe: profile.about_me, language: profile.language })
    setIsEditing(false)
  }

  const updatePref = async (patch: Partial<Preferences>) => {
    if (!prefs) return
    const next = { ...prefs, ...patch }
    setPrefs(next)
    try {
      await savePreferences(next)
    } catch {
      setError("Impossible d'enregistrer les préférences.")
    }
  }

  const handleDeleteAccount = async () => {
    try {
      await requestAccountDeletion()
      setDeleteRequested(true)
      setConfirmingDelete(false)
    } catch {
      setError("Impossible d'envoyer la demande de suppression.")
    }
  }

  if (authed === false) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour voir votre profil.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  if (loading || !profile || !prefs) {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Chargement…</div>
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8 md:py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Profil</h1>
          <p className="text-sm text-muted-foreground">Vos informations et préférences de conversation.</p>
        </div>
        {!isEditing ? (
          <Button onClick={() => setIsEditing(true)} variant="outline">
            <Pencil className="h-4 w-4" strokeWidth={1.75} />
            Modifier
          </Button>
        ) : (
          <div className="flex gap-2">
            <Button variant="ghost" onClick={handleCancel}>
              <X className="h-4 w-4" strokeWidth={1.75} />
              Annuler
            </Button>
            <Button onClick={handleSave}>
              <Check className="h-4 w-4" strokeWidth={1.75} />
              Enregistrer
            </Button>
          </div>
        )}
      </div>

      {error && (
        <p className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
          {error}
        </p>
      )}
      {saved && (
        <p className="rounded-md border border-success/20 bg-success/10 px-4 py-2.5 text-sm text-success">
          Modifications enregistrées.
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Informations personnelles</CardTitle>
          <CardDescription>
            Ce que votre assistant sait de vous — visible par vous seul, sauf mention contraire des consentements.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center gap-5">
            <Avatar className="h-16 w-16 border">
              <AvatarFallback className="bg-accent text-lg font-medium text-accent-foreground">
                {(draft.displayName || "?").slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <div>
              <p className="text-lg font-medium tracking-tight">{draft.displayName || "Sans nom affiché"}</p>
              {profile.onboarding_completed_at && (
                <p className="text-sm text-muted-foreground">
                  Membre depuis {new Date(profile.onboarding_completed_at).toLocaleDateString("fr-FR")}
                </p>
              )}
            </div>
          </div>

          <Separator />

          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="displayName">Nom affiché</Label>
              <Input
                id="displayName"
                value={draft.displayName}
                disabled={!isEditing}
                onChange={(e) => setDraft({ ...draft, displayName: e.target.value })}
              />
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="aboutMe">À propos de moi</Label>
              <Textarea
                id="aboutMe"
                value={draft.aboutMe}
                disabled={!isEditing}
                onChange={(e) => setDraft({ ...draft, aboutMe: e.target.value })}
                rows={3}
                placeholder="Un peu de contexte que l'assistant pourra prendre en compte."
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="language">Langue</Label>
              <select
                id="language"
                value={draft.language}
                disabled={!isEditing}
                className={selectClass}
                onChange={(e) => setDraft({ ...draft, language: e.target.value as "fr" | "en" })}
              >
                <option value="fr">Français</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Style de conversation</CardTitle>
          <CardDescription>Ajustez la manière dont votre assistant vous répond.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Ton</Label>
              <select className={selectClass} value={prefs.tone} onChange={(e) => updatePref({ tone: e.target.value as Preferences["tone"] })}>
                <option value="warm">Chaleureux</option>
                <option value="neutral">Neutre</option>
                <option value="direct">Direct</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Longueur des réponses</Label>
              <select
                className={selectClass}
                value={prefs.response_length}
                onChange={(e) => updatePref({ response_length: e.target.value as Preferences["response_length"] })}
              >
                <option value="short">Courtes</option>
                <option value="medium">Moyennes</option>
                <option value="detailed">Détaillées</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Fréquence des questions</Label>
              <select
                className={selectClass}
                value={prefs.question_frequency}
                onChange={(e) => updatePref({ question_frequency: e.target.value as Preferences["question_frequency"] })}
              >
                <option value="low">Faible</option>
                <option value="medium">Moyenne</option>
                <option value="high">Élevée</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Directivité</Label>
              <select
                className={selectClass}
                value={prefs.directiveness}
                onChange={(e) => updatePref({ directiveness: e.target.value as Preferences["directiveness"] })}
              >
                <option value="reflective">Réflexif</option>
                <option value="balanced">Équilibré</option>
                <option value="directive">Directif</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-destructive/20">
        <CardHeader>
          <CardTitle className="text-destructive">Zone sensible</CardTitle>
          <CardDescription>Cette action est irréversible.</CardDescription>
        </CardHeader>
        <CardContent>
          {deleteRequested ? (
            <p className="text-sm text-muted-foreground">Votre demande de suppression a été enregistrée.</p>
          ) : confirmingDelete ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-destructive/5 p-3">
              <p className="text-sm">Confirmer la suppression définitive de votre compte ?</p>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => setConfirmingDelete(false)}>
                  Annuler
                </Button>
                <Button variant="destructive" size="sm" onClick={handleDeleteAccount}>
                  Confirmer
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Supprimer mon compte</p>
                <p className="text-sm text-muted-foreground">Toutes vos données seront effacées.</p>
              </div>
              <Button variant="outline" className="border-destructive/30 text-destructive hover:bg-destructive/10" onClick={() => setConfirmingDelete(true)}>
                Supprimer
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
