"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { AnalyticsOverview, getAnalyticsOverview } from "@/lib/api"

const EVENT_LABELS: Record<string, string> = {
  conversation_started: "Conversations reprises",
  conversation_new: "Nouvelles conversations",
  message_sent: "Messages envoyés",
  phq9_completed: "Check-ins PHQ-9",
  goal_created: "Objectifs créés",
  assistant_response_generated: "Réponses générées",
}

/**
 * Tableau de bord analytics produit (Phase 15). Alimenté uniquement par
 * `analytics_events`, jamais par une jointure sur une table clinique — les
 * comptes ci-dessous portent sur des pseudonymes rotatifs, pas des patients
 * identifiés. Partagé entre la console admin et l'espace chercheur.
 */
export function AnalyticsPanel() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAnalyticsOverview(14)
      .then(setData)
      .catch(() => setError("Impossible de charger les analytics."))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!data) return null

  const totalEvents = Object.values(data.totals_by_event_type).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-6">
      <Card className="border-primary/15 bg-accent/30">
        <CardContent className="p-4 text-xs text-muted-foreground">
          Basé sur des pseudonymes rotatifs (renouvelés chaque semaine), jamais sur l&apos;identité du patient —
          aucune table clinique n&apos;est lue par ce tableau de bord. Événements produit comptés uniquement pour
          les comptes ayant un consentement Analyses actif.
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        {(Object.keys(EVENT_LABELS) as (keyof typeof EVENT_LABELS)[]).map((key) => (
          <Card key={key}>
            <CardContent className="p-4">
              <p className="text-2xl font-semibold tabular-nums tracking-tight">
                {data.totals_by_event_type[key] ?? 0}
              </p>
              <p className="text-sm text-muted-foreground">{EVENT_LABELS[key]}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Utilisateurs actifs par jour</CardTitle>
          <CardDescription>14 derniers jours, comptés par pseudonyme unique.</CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          {data.daily_active_users.length === 0 ? (
            <p className="text-sm text-muted-foreground">Pas encore de données.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.daily_active_users}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="var(--color-primary)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Messages envoyés par jour</CardTitle>
        </CardHeader>
        <CardContent className="h-64">
          {data.messages_per_day.length === 0 ? (
            <p className="text-sm text-muted-foreground">Pas encore de données.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.messages_per_day}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Réponses IA par chemin de génération</CardTitle>
          <CardDescription>{totalEvents > 0 ? `${data.ai_responses_by_path_and_level.reduce((a, r) => a + r.count, 0)} réponses sur 14 jours.` : "Pas encore de données."}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.ai_responses_by_path_and_level.map((r) => (
            <div key={`${r.generation_path}-${r.decision_level}`} className="flex items-center justify-between text-sm">
              <span>
                {r.generation_path} · <span className="text-muted-foreground">{r.decision_level}</span>
              </span>
              <span className="tabular-nums font-medium">{r.count}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
