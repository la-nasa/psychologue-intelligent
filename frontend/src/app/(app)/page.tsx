"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { ArrowRight, Mic, Activity, Target } from "lucide-react"
import { getProfile, getToken, GoalItem, listGoals, ProfileData } from "@/lib/api"

export default function Home() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [goals, setGoals] = useState<GoalItem[]>([])

  useEffect(() => {
    if (!getToken()) {
      setAuthed(false)
      return
    }
    setAuthed(true)
    getProfile().then(setProfile).catch(() => {})
    listGoals()
      .then((items) => setGoals(items.filter((g) => g.status === "ACTIVE").slice(0, 3)))
      .catch(() => {})
  }, [])

  const greetingName = profile?.display_name?.trim()
  const hour = new Date().getHours()
  const salutation = hour < 12 ? "Bonjour" : hour < 18 ? "Bon après-midi" : "Bonsoir"

  return (
    <div className="mx-auto w-full max-w-3xl space-y-10 px-6 py-10 md:py-14">
      <div className="space-y-1.5">
        <h1 className="text-3xl font-semibold tracking-tight text-balance">
          {salutation}{greetingName ? `, ${greetingName}` : ""}
        </h1>
        <p className="text-muted-foreground">Comment vous sentez-vous aujourd&apos;hui ?</p>
      </div>

      {authed === false && (
        <Card className="border-primary/20 bg-accent/40">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
            <p className="text-sm text-foreground/80">Connectez-vous pour accéder à vos conversations et objectifs.</p>
            <Button asChild size="sm">
              <Link href="/login">Se connecter</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Action principale */}
      <Link href="/conversation" className="group block">
        <Card className="border-primary/15 transition-all hover:border-primary/30 hover:shadow-soft-lg">
          <CardContent className="flex items-center justify-between gap-6 p-6">
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wide text-primary">Reprendre le fil</p>
              <p className="text-lg font-medium tracking-tight">Commencer une conversation</p>
              <p className="text-sm text-muted-foreground">Un espace confidentiel, à votre rythme.</p>
            </div>
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform group-hover:translate-x-0.5">
              <ArrowRight className="h-5 w-5" strokeWidth={1.75} />
            </div>
          </CardContent>
        </Card>
      </Link>

      {/* Actions secondaires */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Link
          href="/voice"
          className="flex items-center gap-3 rounded-lg border px-4 py-3.5 text-sm transition-colors hover:border-foreground/20 hover:bg-accent/40"
        >
          <Mic className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
          <span className="font-medium">Session vocale</span>
          <span className="ml-auto text-xs text-muted-foreground">Bientôt</span>
        </Link>
        <Link
          href="/checkin"
          className="flex items-center gap-3 rounded-lg border px-4 py-3.5 text-sm transition-colors hover:border-foreground/20 hover:bg-accent/40"
        >
          <Activity className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
          <span className="font-medium">Check-in rapide</span>
          <ArrowRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
        </Link>
      </div>

      {/* Objectifs */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Target className="h-4 w-4 text-primary" strokeWidth={1.75} />
            Vos objectifs
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {authed === false ? (
            <p className="text-sm text-muted-foreground">Connectez-vous pour voir vos objectifs.</p>
          ) : goals.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aucun objectif actif pour le moment.{" "}
              <Link href="/goals" className="font-medium text-primary underline-offset-4 hover:underline">
                En créer un
              </Link>
            </p>
          ) : (
            goals.map((goal) => (
              <div key={goal.id} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{goal.title}</span>
                  <span className="tabular-nums text-muted-foreground">{goal.progress}%</span>
                </div>
                <Progress value={goal.progress} className="h-1.5" />
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
