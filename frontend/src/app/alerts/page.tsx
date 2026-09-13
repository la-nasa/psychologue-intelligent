"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { AlertTriangle, Bell, CheckCircle } from "lucide-react"
import { ApiError, ClinicianAlertItem, clearToken, getToken, listClinicianAlerts } from "@/lib/api"

type ViewState = "checking" | "anonymous" | "forbidden" | "ready" | "error"

const SEVERITY_STYLE: Record<string, string> = {
  RED: "bg-red-100 text-red-800",
  ORANGE: "bg-orange-100 text-orange-800",
  GREEN: "bg-green-100 text-green-800",
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
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <AlertTriangle className="h-8 w-8 text-muted-foreground" />
        <p className="max-w-md text-sm text-muted-foreground">
          Ce centre d&apos;alertes est réservé aux rôles clinicien (PSYCHOLOGIST / CLINICAL_SUPERVISOR). Votre compte
          patient n&apos;y a pas accès — c&apos;est le comportement attendu du contrôle d&apos;accès côté serveur,
          pas une erreur.
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
    <div className="flex h-full flex-col">
      <div className="border-b p-6">
        <h2 className="text-2xl font-bold tracking-tight">Centre d&apos;alertes</h2>
        <p className="text-muted-foreground">Alertes de sécurité et de suivi pour vos patients</p>
      </div>

      <ScrollArea className="flex-1 p-6">
        {alerts.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucune alerte.</p>
        ) : (
          <div className="space-y-4">
            {alerts.map((alert) => (
              <Card key={alert.id}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <Bell className="h-5 w-5 text-muted-foreground" />
                      <div>
                        <CardTitle className="text-base">Patient {alert.patient_id.slice(0, 8)}…</CardTitle>
                        <CardDescription>
                          Source : {alert.source}
                          {alert.score !== null ? ` · score ${alert.score}` : ""}
                        </CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge className={SEVERITY_STYLE[alert.level] ?? ""}>{alert.level}</Badge>
                      <Badge variant="outline">
                        <CheckCircle className="mr-1 h-3 w-3" />
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
