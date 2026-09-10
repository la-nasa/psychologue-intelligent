"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { AlertTriangle, Bell, CheckCircle, Clock, Filter, ArrowUpDown } from "lucide-react"

interface Alert {
  id: string
  severity: "green" | "orange" | "red"
  title: string
  description: string
  patientName: string
  createdAt: Date
  status: "new" | "acknowledged" | "in_review" | "resolved" | "closed"
  assignedTo?: string
  slaDeadline?: Date
}

export default function AlertsPage() {
  const [alerts] = useState<Alert[]>([
    {
      id: "1",
      severity: "red",
      title: "Signal de crise détecté",
      description: "Expressions de détresse importante et pensées sombres répétées",
      patientName: "Patient A",
      createdAt: new Date("2024-03-15T11:30:00"),
      status: "new",
      slaDeadline: new Date("2024-03-15T12:30:00"),
    },
    {
      id: "2",
      severity: "orange",
      title: "Détérioration de l'humeur",
      description: "Tendance à la baisse sur 7 jours consécutifs",
      patientName: "Patient B",
      createdAt: new Date("2024-03-15T09:15:00"),
      status: "acknowledged",
      assignedTo: "Dr. Martin",
      slaDeadline: new Date("2024-03-15T17:15:00"),
    },
    {
      id: "3",
      severity: "orange",
      title: "Absence de check-in",
      description: "Aucune interaction depuis 5 jours",
      patientName: "Patient C",
      createdAt: new Date("2024-03-14T08:00:00"),
      status: "in_review",
      assignedTo: "Dr. Dupont",
      slaDeadline: new Date("2024-03-15T08:00:00"),
    },
    {
      id: "4",
      severity: "green",
      title: "Progression notable",
      description: "Amélioration significative des scores PHQ-9",
      patientName: "Patient D",
      createdAt: new Date("2024-03-13T14:20:00"),
      status: "resolved",
      assignedTo: "Dr. Martin",
    },
    {
      id: "5",
      severity: "green",
      title: "Objectif atteint",
      description: "Patient a complété son objectif de routine quotidienne",
      patientName: "Patient E",
      createdAt: new Date("2024-03-12T16:45:00"),
      status: "closed",
      assignedTo: "Dr. Dupont",
    },
  ])

  const getSeverityColor = (severity: "green" | "orange" | "red") => {
    switch (severity) {
      case "red":
        return "bg-red-100 text-red-800 border-red-300"
      case "orange":
        return "bg-orange-100 text-orange-800 border-orange-300"
      case "green":
        return "bg-green-100 text-green-800 border-green-300"
    }
  }

  const getStatusBadge = (status: Alert["status"]) => {
    const variants: Record<Alert["status"], "default" | "secondary" | "outline" | "destructive"> = {
      new: "default",
      acknowledged: "secondary",
      in_review: "outline",
      resolved: "default",
      closed: "secondary",
    }
    
    const labels: Record<Alert["status"], string> = {
      new: "Nouveau",
      acknowledged: "Reconnu",
      in_review: "En revue",
      resolved: "Résolu",
      closed: "Fermé",
    }
    
    return (
      <Badge variant={variants[status]} className="text-xs">
        {labels[status]}
      </Badge>
    )
  }

  const getSeverityIcon = (severity: "green" | "orange" | "red") => {
    switch (severity) {
      case "red":
        return <AlertTriangle className="h-5 w-5 text-red-600" />
      case "orange":
        return <Bell className="h-5 w-5 text-orange-600" />
      case "green":
        return <CheckCircle className="h-5 w-5 text-green-600" />
    }
  }

  const isSlaBreached = (alert: Alert) => {
    if (!alert.slaDeadline) return false
    return new Date() > alert.slaDeadline && alert.status !== "resolved" && alert.status !== "closed"
  }

  const filteredAlerts = alerts.sort((a, b) => {
    const severityOrder = { red: 0, orange: 1, green: 2 }
    return severityOrder[a.severity] - severityOrder[b.severity]
  })

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Centre d'Alertes</h2>
            <p className="text-muted-foreground">
              Suivez et gérez les alertes cliniques
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline">
              <Filter className="mr-2 h-4 w-4" />
              Filtres
            </Button>
            <Button variant="outline">
              <ArrowUpDown className="mr-2 h-4 w-4" />
              Trier
            </Button>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid gap-4 p-6 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Nouvelles</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {alerts.filter((a) => a.status === "new").length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Critiques</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {alerts.filter((a) => a.severity === "red" && a.status !== "closed").length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">En attente</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {alerts.filter((a) => a.status === "in_review").length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">SLA dépassé</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {alerts.filter(isSlaBreached).length}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Alerts List */}
      <ScrollArea className="flex-1 px-6">
        <div className="space-y-4 pb-6">
          {filteredAlerts.map((alert) => (
            <Card key={alert.id} className={isSlaBreached(alert) ? "border-red-300 bg-red-50" : ""}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className="mt-1">{getSeverityIcon(alert.severity)}</div>
                    <div className="space-y-1">
                      <CardTitle className="text-base flex items-center gap-2">
                        {alert.title}
                        {isSlaBreached(alert) && (
                          <Badge variant="destructive" className="text-xs">
                            SLA dépassé
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="flex items-center gap-2">
                        <span>{alert.patientName}</span>
                        <span>•</span>
                        <span>
                          {alert.createdAt.toLocaleDateString("fr-FR", {
                            day: "numeric",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        {alert.assignedTo && (
                          <>
                            <span>•</span>
                            <span>Assigné à {alert.assignedTo}</span>
                          </>
                        )}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={getSeverityColor(alert.severity)}>
                      {alert.severity.toUpperCase()}
                    </Badge>
                    {getStatusBadge(alert.status)}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">{alert.description}</p>
                <div className="flex items-center justify-between">
                  {alert.slaDeadline && (
                    <div className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      SLA: {alert.slaDeadline.toLocaleTimeString("fr-FR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  )}
                  <div className="flex gap-2">
                    {alert.status === "new" && (
                      <>
                        <Button variant="outline" size="sm">
                          Ignorer
                        </Button>
                        <Button size="sm">
                          <CheckCircle className="mr-2 h-4 w-4" />
                          Reconnaître
                        </Button>
                      </>
                    )}
                    {alert.status === "acknowledged" && (
                      <Button size="sm">
                        En revue
                      </Button>
                    )}
                    {alert.status === "in_review" && (
                      <Button size="sm" variant="secondary">
                        Résoudre
                      </Button>
                    )}
                    <Button variant="ghost" size="sm">
                      Détails
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
