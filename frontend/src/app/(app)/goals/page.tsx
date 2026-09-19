"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Target, Plus, CheckCircle2 } from "lucide-react"
import { PageShell, PageHeader } from "@/components/layout/PageShell"
import { AuthGate, EmptyState, PageSkeleton } from "@/components/layout/EmptyState"
import { StatStrip } from "@/components/layout/StatStrip"
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
    return <AuthGate message="Connectez-vous pour voir vos objectifs." />
  }

  const activeGoals = goals.filter((g) => g.status === "ACTIVE")
  const completedGoals = goals.filter((g) => g.status !== "ACTIVE")

  return (
    <PageShell>
      <PageHeader
        title="Objectifs"
        description="Suivez votre progression, à votre rythme."
        actions={
          <Button onClick={() => setShowForm((v) => !v)} variant={showForm ? "outline" : "default"}>
            <Plus className="h-4 w-4" strokeWidth={1.5} />
            Nouvel objectif
          </Button>
        }
      />

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
        <PageSkeleton lines={3} />
      ) : goals.length === 0 ? (
        <EmptyState
          icon={Target}
          title="Aucun objectif pour le moment"
          description="Un objectif clair aide à mesurer vos progrès dans le temps."
        />
      ) : (
        <>
          <StatStrip
            items={[
              { label: "Actifs", value: activeGoals.length },
              {
                label: "Progression",
                value: `${Math.round(activeGoals.reduce((acc, g) => acc + g.progress, 0) / (activeGoals.length || 1))}%`,
              },
              { label: "Atteints", value: completedGoals.length },
            ]}
          />

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
    </PageShell>
  )
}
