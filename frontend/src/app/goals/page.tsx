"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Target, Plus, CheckCircle2, Circle, TrendingUp } from "lucide-react"
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
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Objectifs</h2>
            <p className="text-muted-foreground">Suivez votre progression vers vos objectifs personnels</p>
          </div>
          <Button onClick={() => setShowForm((v) => !v)}>
            <Plus className="mr-2 h-4 w-4" />
            Nouvel objectif
          </Button>
        </div>
      </div>

      {error && <p className="border-b bg-destructive/10 p-2 text-center text-sm text-destructive">{error}</p>}

      {showForm && (
        <form onSubmit={handleCreate} className="space-y-3 border-b p-6">
          <Input placeholder="Titre de l'objectif" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <Input
            placeholder="Description (optionnelle)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Button type="submit" disabled={submitting}>
            {submitting ? "..." : "Créer"}
          </Button>
        </form>
      )}

      {/* Content */}
      <div className="flex-1 space-y-6 p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : goals.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucun objectif pour le moment. Créez-en un pour commencer à suivre votre progression.
          </p>
        ) : (
          <>
            {/* Summary Cards */}
            <div className="grid gap-4 md:grid-cols-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Objectifs actifs</CardTitle>
                  <Target className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{activeGoals.length}</div>
                  <p className="text-xs text-muted-foreground">{completedGoals.length} atteints</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Progression moyenne</CardTitle>
                  <TrendingUp className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {Math.round(activeGoals.reduce((acc, g) => acc + g.progress, 0) / (activeGoals.length || 1))}%
                  </div>
                  <p className="text-xs text-muted-foreground">Sur les objectifs en cours</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Taux de réussite</CardTitle>
                  <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{Math.round((completedGoals.length / goals.length) * 100)}%</div>
                  <p className="text-xs text-muted-foreground">Objectifs atteints</p>
                </CardContent>
              </Card>
            </div>

            {/* Active Goals */}
            {activeGoals.length > 0 && (
              <div>
                <h3 className="mb-4 text-lg font-semibold">Objectifs en cours</h3>
                <div className="grid gap-4 md:grid-cols-2">
                  {activeGoals.map((goal) => (
                    <Card key={goal.id}>
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <Circle className="h-5 w-5 text-primary" />
                            <CardTitle className="text-base">{goal.title}</CardTitle>
                          </div>
                          <Badge variant="secondary">{goal.progress}%</Badge>
                        </div>
                        {goal.description && <CardDescription className="text-sm">{goal.description}</CardDescription>}
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <Progress value={goal.progress} className="h-2" />
                        <Button variant="ghost" size="sm" onClick={() => bump(goal.id, goal.progress)}>
                          + 10% de progression
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {/* Completed Goals */}
            {completedGoals.length > 0 && (
              <div>
                <h3 className="mb-4 text-lg font-semibold">Objectifs atteints</h3>
                <div className="grid gap-4 md:grid-cols-2">
                  {completedGoals.map((goal) => (
                    <Card key={goal.id} className="opacity-75">
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 text-green-600" />
                            <CardTitle className="text-base">{goal.title}</CardTitle>
                          </div>
                          <Badge variant="default">Atteint</Badge>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <Progress value={goal.progress} className="h-2" />
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
