"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ShieldAlert, BellRing, CheckCircle } from "lucide-react"
import { ApiError, ClinicianAlertItem, clearToken, getToken, listClinicianAlerts } from "@/lib/api"

type ViewState = "checking" | "anonymous" | "forbidden" | "ready" | "error"

const SEVERITY_VARIANT: Record<string, "destructive" | "warning" | "success" | "secondary"> = {
  RED: "destructive",
  ORANGE: "warning",
  GREEN: "success",
}

export default function AlertsPage() {
  const [state, setState] = useState<ViewState>("checking")
  const [alerts, setAlerts] = useState<ClinicianAlertItem[]>([])

  useEffect(() => {
    if (!getToken()) {
      setState("anonymous")
      return
    }
    listClinicianAlerts()
      .then((items) => {
        setAlerts(items)
        setState("ready")
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          setState("anonymous")
        } else if (err instanceof ApiError && err.status === 403) {
          setState("forbidden")
        } else {
          setState("error")
        }
      })
  }, [])

  if (state === "checking") {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Chargement…</div>
  }

  if (state === "anonymous") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour voir les alertes.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  if (state === "forbidden") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <ShieldAlert className="h-8 w-8 text-muted-foreground/50" strokeWidth={1.5} />
        <p className="max-w-md text-sm text-muted-foreground">
          Ce centre d&apos;alertes est réservé aux cliniciens référents. Votre compte patient n&apos;y a pas
          accès — c&apos;est le comportement attendu, pas une erreur.
        </p>
      </div>
    )
  }

  if (state === "error") {
    return (
      <div className="flex h-full items-center justify-center text-sm text-destructive">
        Impossible de charger les alertes. Le serveur est-il démarré ?
      </div>
    )
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="space-y-1 px-6 pb-4 pt-8 md:pt-10">
        <h1 className="text-2xl font-semibold tracking-tight">Centre d&apos;alertes</h1>
        <p className="text-sm text-muted-foreground">Alertes de sécurité et de suivi pour vos patients référés.</p>
      </div>

      <ScrollArea className="flex-1 px-6 pb-8">
        {alerts.length === 0 ? (
          <div className="rounded-lg border border-dashed p-10 text-center">
            <BellRing className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">Aucune alerte active.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map((alert) => (
              <Card key={alert.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-base">Patient {alert.patient_id.slice(0, 8)}…</CardTitle>
                      <CardDescription>
                        {alert.source}
                        {alert.score !== null ? ` · score ${alert.score}` : ""}
                      </CardDescription>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Badge variant={SEVERITY_VARIANT[alert.level] ?? "secondary"}>{alert.level}</Badge>
                      <Badge variant="outline">
                        <CheckCircle className="h-3 w-3" strokeWidth={1.75} />
                        {alert.status}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <p>Créée le {new Date(alert.created_at).toLocaleString("fr-FR")}</p>
                  {alert.sla_due_at && <p>SLA : {new Date(alert.sla_due_at).toLocaleString("fr-FR")}</p>}
                  {alert.acknowledged_at && (
                    <p>Prise en compte le {new Date(alert.acknowledged_at).toLocaleString("fr-FR")}</p>
                  )}
                  {alert.assigned_clinician_id && <p>Assignée à {alert.assigned_clinician_id.slice(0, 8)}…</p>}
                  {alert.policy_version && <p>Politique : {alert.policy_version}</p>}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
