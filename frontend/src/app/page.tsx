"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { MessageCircle, Mic, Activity, Target } from "lucide-react"
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

  return (
    <div className="flex-1 space-y-8 p-6 pt-6">
      {/* Welcome Section */}
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight">
          Bonjour{greetingName ? ` ${greetingName}` : ""}
        </h1>
        <p className="text-muted-foreground">Comment vous sentez-vous aujourd&apos;hui ?</p>
      </div>

      {authed === false && (
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <p className="text-sm text-muted-foreground">Connectez-vous pour accéder à vos conversations et objectifs.</p>
            <Button asChild size="sm">
              <Link href="/login">Se connecter</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">Commencer une conversation</CardTitle>
            <CardDescription>Discutez avec notre assistant IA</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" size="lg" asChild>
              <Link href="/conversation">
                <MessageCircle className="mr-2 h-5 w-5" />
                Conversation texte
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">Session vocale</CardTitle>
            <CardDescription>Parlez naturellement avec l&apos;IA</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" variant="outline" size="lg" asChild>
              <Link href="/voice">
                <Mic className="mr-2 h-5 w-5" />
                Conversation vocale
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">Check-in rapide</CardTitle>
            <CardDescription>Évaluez votre humeur du moment</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" variant="secondary" size="lg" disabled title="Pas encore implémenté côté écran">
              <Activity className="mr-2 h-5 w-5" />
              Check-in (à venir)
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Goals Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            Vos objectifs
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {authed === false ? (
            <p className="text-sm text-muted-foreground">Connectez-vous pour voir vos objectifs.</p>
          ) : goals.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aucun objectif actif.{" "}
              <Link href="/goals" className="underline">
                En créer un
              </Link>
              .
            </p>
          ) : (
            goals.map((goal) => (
              <div key={goal.id} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span>{goal.title}</span>
                  <span className="text-muted-foreground">{goal.progress}%</span>
                </div>
                <Progress value={goal.progress} className="h-2" />
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
