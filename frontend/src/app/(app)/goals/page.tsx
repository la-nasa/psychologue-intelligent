"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Target, Plus, CheckCircle2, TrendingUp } from "lucide-react"
import { ApiError, clearToken, createGoal, getToken, GoalItem, listGoals, recordGoalProgress } from "@/lib/api"

export default function GoalsPage() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [goals, setGoals] = useState<GoalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const refresh = () => {
    setLoading(true)
    listGoals()
      .then((items) => {
        setGoals(items)
        setError(null)
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          setAuthed(false)
        } else {
          setError("Impossible de charger les objectifs.")
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!getToken()) {
      setAuthed(false)
      return
    }
    setAuthed(true)
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSubmitting(true)
    try {
      await createGoal(title.trim(), description.trim())
      setTitle("")
      setDescription("")
      setShowForm(false)
      refresh()
    } catch {
      setError("Impossible de créer l'objectif.")
    } finally {
      setSubmitting(false)
    }
  }

  const bump = async (goalId: string, current: number) => {
    const next = Math.min(100, current + 10)
    try {
      await recordGoalProgress(goalId, next)
      refresh()
    } catch {
      setError("Impossible de mettre à jour la progression.")
    }
  }

  if (authed === false) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour voir vos objectifs.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  const activeGoals = goals.filter((g) => g.status === "ACTIVE")
  const completedGoals = goals.filter((g) => g.status !== "ACTIVE")

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-6 py-8 md:py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Objectifs</h1>
          <p className="text-sm text-muted-foreground">Suivez votre progression, à votre rythme.</p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)} variant={showForm ? "outline" : "default"}>
          <Plus className="h-4 w-4" strokeWidth={1.75} />
          Nouvel objectif
        </Button>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
          {error}
        </p>
      )}

      {showForm && (
        <Card>
          <CardContent className="space-y-3 p-5">
            <form onSubmit={handleCreate} className="space-y-3">
              <Input placeholder="Titre de l'objectif" value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
              <Input
                placeholder="Description (optionnelle)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <Button type="submit" disabled={submitting}>
                {submitting ? "Création…" : "Créer l'objectif"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : goals.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center">
          <Target className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">
            Aucun objectif pour le moment. Un objectif clair aide à mesurer vos progrès dans le temps.
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border p-4">
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-xs font-medium uppercase tracking-wide">Actifs</span>
                <Target className="h-3.5 w-3.5" strokeWidth={1.75} />
              </div>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{activeGoals.length}</p>
            </div>
            <div className="rounded-lg border p-4">
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-xs font-medium uppercase tracking-wide">Progression</span>
                <TrendingUp className="h-3.5 w-3.5" strokeWidth={1.75} />
              </div>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {Math.round(activeGoals.reduce((acc, g) => acc + g.progress, 0) / (activeGoals.length || 1))}%
              </p>
            </div>
            <div className="rounded-lg border p-4">
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-xs font-medium uppercase tracking-wide">Atteints</span>
                <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              </div>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{completedGoals.length}</p>
            </div>
          </div>

          {activeGoals.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-muted-foreground">En cours</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {activeGoals.map((goal) => (
                  <Card key={goal.id}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <CardTitle className="text-base">{goal.title}</CardTitle>
                        <Badge variant="secondary" className="tabular-nums">{goal.progress}%</Badge>
                      </div>
                      {goal.description && <CardDescription>{goal.description}</CardDescription>}
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Progress value={goal.progress} className="h-1.5" />
                      <Button variant="ghost" size="sm" onClick={() => bump(goal.id, goal.progress)} className="-ml-2">
                        + 10% de progression
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {completedGoals.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-muted-foreground">Atteints</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {completedGoals.map((goal) => (
                  <Card key={goal.id} className="bg-muted/40">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between gap-3">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <CheckCircle2 className="h-4 w-4 text-success" strokeWidth={1.75} />
                          {goal.title}
                        </CardTitle>
                        <Badge variant="success">Atteint</Badge>
                      </div>
                    </CardHeader>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
