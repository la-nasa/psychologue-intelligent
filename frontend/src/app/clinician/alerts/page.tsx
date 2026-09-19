"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { AlertTriangle, ArrowUpRight } from "lucide-react"
import { ApiError, AlertActionTarget, ClinicianAlertItem, actOnAlert, listClinicianAlerts } from "@/lib/api"

const LEVEL_VARIANT: Record<string, "destructive" | "warning" | "secondary"> = {
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

export default function ClinicianAlertsPage() {
  const [alerts, setAlerts] = useState<ClinicianAlertItem[] | null>(null)
  const [level, setLevel] = useState<string>("all")
  const [status, setStatus] = useState<string>("all")
  const [error, setError] = useState<string | null>(null)
  const [actingOn, setActingOn] = useState<string | null>(null)

  const refresh = useCallback(() => {
    listClinicianAlerts(level === "all" ? undefined : level, status === "all" ? undefined : status)
      .then(setAlerts)
      .catch(() => setError("Impossible de charger les alertes."))
  }, [level, status])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAction = async (alertId: string, target: AlertActionTarget) => {
    setActingOn(alertId)
    try {
      await actOnAlert(alertId, target)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action impossible sur cette alerte.")
    } finally {
      setActingOn(null)
    }
  }

  const isSlaBreached = (alert: ClinicianAlertItem) =>
    alert.sla_due_at != null && new Date(alert.sla_due_at).getTime() < Date.now()

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-5 py-8 md:px-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Centre d&apos;alertes</h1>
        <p className="text-sm text-muted-foreground">Signaux ORANGE / RED, jamais décidés par le modèle génératif.</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Niveau" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous les niveaux</SelectItem>
            <SelectItem value="RED">RED</SelectItem>
            <SelectItem value="ORANGE">ORANGE</SelectItem>
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Statut" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous les statuts</SelectItem>
            <SelectItem value="OPEN">OPEN</SelectItem>
            <SelectItem value="NOTIFIED">NOTIFIED</SelectItem>
            <SelectItem value="ACKNOWLEDGED">ACKNOWLEDGED</SelectItem>
            <SelectItem value="IN_REVIEW">IN_REVIEW</SelectItem>
            <SelectItem value="ESCALATED">ESCALATED</SelectItem>
            <SelectItem value="RESOLVED">RESOLVED</SelectItem>
            <SelectItem value="CLOSED">CLOSED</SelectItem>
            <SelectItem value="CANCELLED">CANCELLED</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {alerts && alerts.length === 0 && (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">Aucune alerte pour ces filtres.</CardContent></Card>
      )}

      <div className="space-y-3">
        {alerts?.map((alert) => {
          const nextActions = NEXT_ACTIONS[alert.status] ?? []
          return (
            <Card key={alert.id} className={isSlaBreached(alert) ? "border-destructive/40" : undefined}>
              <CardContent className="space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={LEVEL_VARIANT[alert.level] ?? "secondary"}>{alert.level}</Badge>
                    <Badge variant="outline">{alert.status}</Badge>
                    <Link href={`/clinician/patients/${alert.patient_id}`} className="flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                      Dossier patient <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={1.75} />
                    </Link>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(alert.created_at).toLocaleString("fr-FR")}</span>
                </div>
                {alert.sla_due_at && (
                  <p className={`flex items-center gap-1 text-xs ${isSlaBreached(alert) ? "text-destructive" : "text-muted-foreground"}`}>
                    <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />
                    SLA {isSlaBreached(alert) ? "dépassé" : "à respecter"} : {new Date(alert.sla_due_at).toLocaleString("fr-FR")}
                  </p>
                )}
                {nextActions.length > 0 && (
                  <div className="flex flex-wrap gap-2 border-t pt-3">
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
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
