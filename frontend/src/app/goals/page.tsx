"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Target, Plus, CheckCircle2, Circle, TrendingUp } from "lucide-react"

interface Goal {
  id: string
  title: string
  description: string
  progress: number
  status: "active" | "completed" | "paused"
  createdAt: Date
  lastUpdated: Date
}

export default function GoalsPage() {
  const [goals] = useState<Goal[]>([
    {
      id: "1",
      title: "Améliorer le sommeil",
      description: "Établir une routine de coucher régulière et améliorer la qualité du sommeil",
      progress: 70,
      status: "active",
      createdAt: new Date("2024-01-15"),
      lastUpdated: new Date(),
    },
    {
      id: "2",
      title: "Gérer le stress",
      description: "Développer des techniques de gestion du stress au quotidien",
      progress: 45,
      status: "active",
      createdAt: new Date("2024-02-01"),
      lastUpdated: new Date(),
    },
    {
      id: "3",
      title: "Routine quotidienne",
      description: "Mettre en place une routine matinale et soiraine structurée",
      progress: 60,
      status: "active",
      createdAt: new Date("2024-01-20"),
      lastUpdated: new Date(),
    },
    {
      id: "4",
      title: "Activité physique",
      description: "Pratiquer une activité physique régulière 3 fois par semaine",
      progress: 100,
      status: "completed",
      createdAt: new Date("2023-12-01"),
      lastUpdated: new Date("2024-02-15"),
    },
  ])

  const activeGoals = goals.filter((g) => g.status === "active")
  const completedGoals = goals.filter((g) => g.status === "completed")

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Objectifs</h2>
            <p className="text-muted-foreground">
              Suivez votre progression vers vos objectifs personnels
            </p>
          </div>
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Nouvel objectif
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 space-y-6 p-6">
        {/* Summary Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Objectifs actifs</CardTitle>
              <Target className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{activeGoals.length}</div>
              <p className="text-xs text-muted-foreground">
                {completedGoals.length} complétés
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Progression moyenne</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {Math.round(
                  activeGoals.reduce((acc, g) => acc + g.progress, 0) /
                    (activeGoals.length || 1)
                )}%
              </div>
              <p className="text-xs text-muted-foreground">
                Sur les objectifs en cours
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Taux de réussite</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {Math.round(
                  (completedGoals.length / goals.length) * 100
                )}%
              </div>
              <p className="text-xs text-muted-foreground">
                Objectifs atteints
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Active Goals */}
        <div>
          <h3 className="text-lg font-semibold mb-4">Objectifs en cours</h3>
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
                  <CardDescription className="text-sm">
                    {goal.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Progress value={goal.progress} className="h-2" />
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      Créé le {goal.createdAt.toLocaleDateString("fr-FR")}
                    </span>
                    <span>
                      Mis à jour {goal.lastUpdated.toLocaleDateString("fr-FR")}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Completed Goals */}
        {completedGoals.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold mb-4">Objectifs complétés</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {completedGoals.map((goal) => (
                <Card key={goal.id} className="opacity-75">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-5 w-5 text-green-600" />
                        <CardTitle className="text-base">{goal.title}</CardTitle>
                      </div>
                      <Badge variant="default">Complété</Badge>
                    </div>
                    <CardDescription className="text-sm">
                      {goal.description}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Progress value={goal.progress} className="h-2" />
                    <p className="mt-2 text-xs text-muted-foreground">
                      Complété le {goal.lastUpdated.toLocaleDateString("fr-FR")}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
