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
import { User, Edit2, Save, X } from "lucide-react"
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

export default function ProfilePage() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

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
      setTimeout(() => setSaved(false), 2000)
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
    if (!confirm("Cette action est irréversible. Confirmer la suppression du compte ?")) return
    try {
      await requestAccountDeletion()
      alert("Demande de suppression enregistrée.")
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
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Profil</h2>
            <p className="text-muted-foreground">Gérez vos informations personnelles et préférences</p>
          </div>
          {!isEditing ? (
            <Button onClick={() => setIsEditing(true)}>
              <Edit2 className="mr-2 h-4 w-4" />
              Modifier
            </Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleCancel}>
                <X className="mr-2 h-4 w-4" />
                Annuler
              </Button>
              <Button onClick={handleSave}>
                <Save className="mr-2 h-4 w-4" />
                Enregistrer
              </Button>
            </div>
          )}
        </div>
      </div>

      {error && <p className="border-b bg-destructive/10 p-2 text-center text-sm text-destructive">{error}</p>}
      {saved && <p className="border-b bg-emerald-500/10 p-2 text-center text-sm text-emerald-600">Enregistré.</p>}

      {/* Content */}
      <div className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle>Informations personnelles</CardTitle>
            <CardDescription>Ce que l&apos;assistant sait de vous (visible par vous seul, sauf mention contraire des consentements)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center gap-6">
              <Avatar className="h-24 w-24">
                <AvatarFallback className="text-2xl">
                  {(draft.displayName || "?").slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div>
                <h3 className="text-xl font-semibold">{draft.displayName || "(sans nom affiché)"}</h3>
                {profile.onboarding_completed_at && (
                  <p className="text-muted-foreground">
                    Membre depuis {new Date(profile.onboarding_completed_at).toLocaleDateString("fr-FR")}
                  </p>
                )}
              </div>
            </div>

            <Separator />

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="displayName">Nom affiché</Label>
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 text-muted-foreground" />
                  <Input
                    id="displayName"
                    value={draft.displayName}
                    disabled={!isEditing}
                    onChange={(e) => setDraft({ ...draft, displayName: e.target.value })}
                  />
                </div>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="aboutMe">À propos de moi (contexte donné à l&apos;assistant)</Label>
                <Textarea
                  id="aboutMe"
                  value={draft.aboutMe}
                  disabled={!isEditing}
                  onChange={(e) => setDraft({ ...draft, aboutMe: e.target.value })}
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="language">Langue</Label>
                <select
                  id="language"
                  value={draft.language}
                  disabled={!isEditing}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  onChange={(e) => setDraft({ ...draft, language: e.target.value as "fr" | "en" })}
                >
                  <option value="fr">Français</option>
                  <option value="en">English</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Preferences */}
        <Card>
          <CardHeader>
            <CardTitle>Style de conversation</CardTitle>
            <CardDescription>Ajuste la manière dont l&apos;assistant vous répond</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Ton</Label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={prefs.tone}
                  onChange={(e) => updatePref({ tone: e.target.value as Preferences["tone"] })}
                >
                  <option value="warm">Chaleureux</option>
                  <option value="neutral">Neutre</option>
                  <option value="direct">Direct</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Longueur des réponses</Label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={prefs.response_length}
                  onChange={(e) => updatePref({ response_length: e.target.value as Preferences["response_length"] })}
                >
                  <option value="short">Courtes</option>
                  <option value="medium">Moyennes</option>
                  <option value="detailed">Détaillées</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Fréquence des questions</Label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={prefs.question_frequency}
                  onChange={(e) =>
                    updatePref({ question_frequency: e.target.value as Preferences["question_frequency"] })
                  }
                >
                  <option value="low">Faible</option>
                  <option value="medium">Moyenne</option>
                  <option value="high">Élevée</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Directivité</Label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
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

        {/* Account Actions */}
        <Card>
          <CardHeader>
            <CardTitle>Zone dangereuse</CardTitle>
            <CardDescription>Actions irréversibles sur votre compte</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Supprimer mon compte</p>
                <p className="text-sm text-muted-foreground">Cette action est irréversible.</p>
              </div>
              <Button variant="destructive" onClick={handleDeleteAccount}>
                Supprimer
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
