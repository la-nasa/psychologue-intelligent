"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AlertTriangle, TrendingDown, TrendingUp, Minus } from "lucide-react"
import {
  ApiError,
  AlertActionTarget,
  Patient360,
  actOnAlert,
  getPatient360,
} from "@/lib/api"

const ALERT_LEVEL_VARIANT: Record<string, "destructive" | "warning" | "secondary"> = {
  RED: "destructive",
  ORANGE: "warning",
  GREEN: "secondary",
}

const NEXT_ACTIONS: Record<string, AlertActionTarget[]> = {
  OPEN: ["ACKNOWLEDGED", "CANCELLED"],
  NOTIFIED: ["ACKNOWLEDGED", "CANCELLED"],
  ACKNOWLEDGED: ["IN_REVIEW", "RESOLVED"],
  IN_REVIEW: ["ESCALATED", "RESOLVED"],
  ESCALATED: ["RESOLVED"],
}

const ACTION_LABELS: Record<AlertActionTarget, string> = {
  ACKNOWLEDGED: "Accuser réception",
  IN_REVIEW: "Passer en revue",
  ESCALATED: "Escalader",
  RESOLVED: "Résoudre",
  CANCELLED: "Annuler",
}

function TrendIcon({ direction }: { direction: string }) {
  if (direction === "improving") return <TrendingDown className="h-4 w-4 text-success" strokeWidth={1.75} />
  if (direction === "worsening") return <TrendingUp className="h-4 w-4 text-destructive" strokeWidth={1.75} />
  return <Minus className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
}

export default function PatientDetailPage() {
  const params = useParams<{ patientId: string }>()
  const patientId = params.patientId
  const [data, setData] = useState<Patient360 | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [justification, setJustification] = useState<Record<string, string>>({})
  const [actingOn, setActingOn] = useState<string | null>(null)
  const [tab, setTab] = useState("synthese")

  const refresh = useCallback(() => {
    getPatient360(patientId)
      .then(setData)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Impossible de charger ce dossier.")
      })
  }, [patientId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAction = async (alertId: string, target: AlertActionTarget) => {
    setActingOn(alertId)
    try {
      await actOnAlert(alertId, target, justification[alertId] ?? "")
      setJustification((prev) => ({ ...prev, [alertId]: "" }))
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action impossible sur cette alerte.")
    } finally {
      setActingOn(null)
    }
  }

  if (error && !data) {
    return (
      <div className="mx-auto w-full max-w-4xl px-6 py-10">
        <p className="text-sm text-destructive">{error}</p>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{data.display_name || "Patient sans nom"}</h1>
        <p className="text-sm text-muted-foreground">Vue 360 — chaque affirmation renvoie à sa source.</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="synthese">Synthèse</TabsTrigger>
          <TabsTrigger value="phq9">PHQ-9</TabsTrigger>
          <TabsTrigger value="alertes">
            Alertes {data.alerts.length > 0 && <span className="ml-1.5 tabular-nums">({data.alerts.length})</span>}
          </TabsTrigger>
          <TabsTrigger value="objectifs">Objectifs</TabsTrigger>
          <TabsTrigger value="consentements">Consentements</TabsTrigger>
        </TabsList>

        <TabsContent value="synthese" className="space-y-4">
          <Card className="border-primary/15 bg-accent/30">
            <CardContent className="p-4 text-xs text-muted-foreground">{data.summary.disclaimer}</CardContent>
          </Card>
          {data.summary.statements.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune donnée exploitable pour l&apos;instant.</p>
          ) : (
            <div className="space-y-3">
              {data.summary.statements.map((s) => (
                <Card key={s.key}>
                  <CardContent className="space-y-1.5 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <Badge variant="outline" className="capitalize">{s.category}</Badge>
                      {s.as_of && <span className="text-xs text-muted-foreground">{new Date(s.as_of).toLocaleDateString("fr-FR")}</span>}
                    </div>
                    <p className="text-sm">{s.text}</p>
                    <p className="text-xs text-muted-foreground">
                      Pièce{s.evidence.length > 1 ? "s" : ""} justificative{s.evidence.length > 1 ? "s" : ""} : {s.evidence.map((e) => `${e.type}#${e.id.slice(0, 8)}`).join(", ")}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="phq9" className="space-y-4">
          {data.phq9_trend.latest ? (
            <Card>
              <CardContent className="flex items-center gap-4 p-5">
                <TrendIcon direction={data.phq9_trend.direction} />
                <div>
                  <p className="font-medium tracking-tight">
                    Dernier score : {data.phq9_trend.latest.total_score}/27 — {data.phq9_trend.latest.severity_band}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {data.phq9_trend.direction === "improving" && "En amélioration par rapport au précédent."}
                    {data.phq9_trend.direction === "worsening" && "En hausse par rapport au précédent."}
                    {data.phq9_trend.direction === "stable" && "Stable par rapport au précédent."}
                    {data.phq9_trend.direction === "first" && "Premier questionnaire complété."}
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <p className="text-sm text-muted-foreground">Aucun PHQ-9 complété par ce patient.</p>
          )}

          {data.phq9_history.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Score total</TableHead>
                  <TableHead>Item 9 (sûreté)</TableHead>
                  <TableHead>Sévérité</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.phq9_history.map((h) => (
                  <TableRow key={h.id}>
                    <TableCell>{new Date(h.completed_at).toLocaleDateString("fr-FR")}</TableCell>
                    <TableCell className="tabular-nums">{h.total_score}/27</TableCell>
                    <TableCell className="tabular-nums">
                      {h.item9_score > 0 ? <Badge variant="destructive">{h.item9_score}</Badge> : h.item9_score}
                    </TableCell>
                    <TableCell>{h.severity_band}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="alertes" className="space-y-3">
          {data.alerts.length === 0 && <p className="text-sm text-muted-foreground">Aucune alerte pour ce patient.</p>}
          {data.alerts.map((alert) => {
            const nextActions = NEXT_ACTIONS[alert.status] ?? []
            return (
              <Card key={alert.id}>
                <CardContent className="space-y-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge variant={ALERT_LEVEL_VARIANT[alert.level] ?? "secondary"}>{alert.level}</Badge>
                      <Badge variant="outline">{alert.status}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {new Date(alert.created_at).toLocaleString("fr-FR")}
                      </span>
                    </div>
                    {alert.sla_due_at && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />
                        SLA : {new Date(alert.sla_due_at).toLocaleString("fr-FR")}
                      </span>
                    )}
                  </div>
                  {nextActions.length > 0 && (
                    <div className="space-y-2 border-t pt-3">
                      <Textarea
                        placeholder="Justification (optionnelle)"
                        value={justification[alert.id] ?? ""}
                        onChange={(e) => setJustification((prev) => ({ ...prev, [alert.id]: e.target.value }))}
                        className="min-h-16 text-sm"
                      />
                      <div className="flex flex-wrap gap-2">
                        {nextActions.map((target) => (
                          <Button
                            key={target}
                            size="sm"
                            variant={target === "CANCELLED" ? "outline" : "default"}
                            disabled={actingOn === alert.id}
                            onClick={() => handleAction(alert.id, target)}
                          >
                            {ACTION_LABELS[target]}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </TabsContent>

        <TabsContent value="objectifs" className="space-y-3">
          {data.goals.length === 0 && <p className="text-sm text-muted-foreground">Aucun objectif défini.</p>}
          {data.goals.map((g) => (
            <Card key={g.id}>
              <CardContent className="flex items-center justify-between p-4">
                <div>
                  <p className="font-medium">{g.title}</p>
                  <p className="text-xs text-muted-foreground">
                    Créé le {new Date(g.created_at).toLocaleDateString("fr-FR")}
                  </p>
                </div>
                <Badge variant="outline">{g.status}</Badge>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="consentements">
          <Card>
            <CardHeader>
              <CardDescription>Finalité, version, statut — pas de contenu.</CardDescription>
            </CardHeader>
            <CardContent className="divide-y">
              {data.consents.map((c) => (
                <div key={`${c.purpose}-${c.version}`} className="flex items-center justify-between py-2.5 text-sm">
                  <span>{c.purpose}</span>
                  <Badge variant={c.active ? "success" : "outline"}>{c.active ? "Actif" : "Révoqué"}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
