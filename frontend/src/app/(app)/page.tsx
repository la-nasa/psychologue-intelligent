"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ArrowRight, Mic, Activity } from "lucide-react"
import { PageShell } from "@/components/layout/PageShell"
import { getProfile, getToken, GoalItem, listGoals, ProfileData } from "@/lib/api"

export default function Home() {
  const [authed, setAuthed] = useState(false)
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [goals, setGoals] = useState<GoalItem[]>([])
  const [salutation, setSalutation] = useState("Bonjour")
  const [todayLabel, setTodayLabel] = useState("")

  useEffect(() => {
    const hour = new Date().getHours()
    setSalutation(hour < 12 ? "Bonjour" : hour < 18 ? "Bon après-midi" : "Bonsoir")
    setTodayLabel(new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" }))
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

  return (
    <PageShell className="animate-enter">
      <div className="grid gap-10 lg:grid-cols-[1.4fr_0.8fr] lg:items-end">
        <div className="space-y-2">
          <h1 className="max-w-xl text-3xl font-semibold tracking-tight text-balance md:text-4xl">
            {salutation}
            {greetingName ? `, ${greetingName}` : ""}
          </h1>
          <p className="max-w-[42ch] text-muted-foreground">Comment vous sentez-vous aujourd&apos;hui ?</p>
        </div>
        {todayLabel && <p className="hidden text-right text-xs text-muted-foreground lg:block">{todayLabel}</p>}
      </div>

      {!authed && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-y py-4">
          <p className="text-sm text-muted-foreground">Connectez-vous pour retrouver vos conversations.</p>
          <Button asChild size="sm">
            <Link href="/login">Se connecter</Link>
          </Button>
        </div>
      )}

      <Link
        href="/conversation"
        className="group flex items-center justify-between gap-6 rounded-2xl border border-primary/15 bg-card px-6 py-6 shadow-soft transition-colors hover:border-primary/30"
      >
        <div className="space-y-1">
          <p className="text-xs font-medium tracking-wide text-primary">Reprendre</p>
          <p className="text-lg font-medium tracking-tight">Ouvrir l&apos;entretien</p>
          <p className="text-sm text-muted-foreground">Un espace confidentiel, à votre rythme.</p>
        </div>
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform group-hover:translate-x-0.5 group-active:scale-[0.98]">
          <ArrowRight className="h-5 w-5" strokeWidth={1.5} />
        </div>
      </Link>

      <div className="divide-y border-y">
        <Link href="/voice" className="flex min-h-14 items-center gap-3 py-3.5 text-sm transition-colors hover:text-primary">
          <Mic className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
          <span className="font-medium">Session vocale</span>
          <ArrowRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
        </Link>
        <Link href="/checkin" className="flex min-h-14 items-center gap-3 py-3.5 text-sm transition-colors hover:text-primary">
          <Activity className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
          <span className="font-medium">Check-in rapide</span>
          <ArrowRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
        </Link>
      </div>

      <section className="space-y-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium tracking-tight">Objectifs en cours</h2>
          <Button asChild variant="ghost" size="sm" className="-mr-2 text-muted-foreground">
            <Link href="/goals">Tous</Link>
          </Button>
        </div>
        {!authed ? (
          <p className="text-sm text-muted-foreground">Connectez-vous pour voir vos objectifs.</p>
        ) : goals.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucun objectif actif.{" "}
            <Link href="/goals" className="font-medium text-primary underline-offset-4 hover:underline">
              En créer un
            </Link>
          </p>
        ) : (
          <ul className="space-y-4">
            {goals.map((goal) => (
              <li key={goal.id} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{goal.title}</span>
                  <span className="font-mono tabular-nums text-muted-foreground">{goal.progress}%</span>
                </div>
                <Progress value={goal.progress} className="h-1.5" />
              </li>
            ))}
          </ul>
        )}
      </section>
    </PageShell>
  )
}
