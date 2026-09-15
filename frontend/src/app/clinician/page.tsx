"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { AlertTriangle, Users, TimerReset, Inbox, ArrowRight } from "lucide-react"
import { ClinicianOverview, getClinicianOverview } from "@/lib/api"

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: React.ElementType
  label: string
  value: number
  tone?: "default" | "danger" | "warning"
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
            tone === "danger"
              ? "bg-destructive/10 text-destructive"
              : tone === "warning"
                ? "bg-warning/10 text-warning"
                : "bg-accent text-accent-foreground"
          }`}
        >
          <Icon className="h-5 w-5" strokeWidth={1.75} />
        </div>
        <div>
          <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export default function ClinicianOverviewPage() {
  const [overview, setOverview] = useState<ClinicianOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getClinicianOverview()
      .then(setOverview)
      .catch(() => setError("Impossible de charger la vue d'ensemble."))
  }, [])

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Vue d&apos;ensemble</h1>
        <p className="text-sm text-muted-foreground">Votre file de travail du jour.</p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {overview && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={Users} label="Patients suivis" value={overview.patients_followed} />
          <StatCard icon={AlertTriangle} label="Alertes rouges ouvertes" value={overview.open_alerts.red} tone="danger" />
          <StatCard icon={Inbox} label="Alertes orange ouvertes" value={overview.open_alerts.orange} tone="warning" />
          <StatCard icon={TimerReset} label="SLA dépassés" value={overview.sla_breached} tone={overview.sla_breached > 0 ? "danger" : "default"} />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/clinician/alerts" className="group block">
          <Card className="transition-all hover:border-primary/30 hover:shadow-soft-lg">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                Centre d&apos;alertes
                <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" strokeWidth={1.75} />
              </CardTitle>
              <CardDescription>Alertes ORANGE / RED, avec délais SLA et actions de cycle de vie.</CardDescription>
            </CardHeader>
          </Card>
        </Link>
        <Link href="/clinician/patients" className="group block">
          <Card className="transition-all hover:border-primary/30 hover:shadow-soft-lg">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                Patients suivis
                <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" strokeWidth={1.75} />
              </CardTitle>
              <CardDescription>Dossier, synthèse corrélationnelle et historique PHQ-9 de chaque patient.</CardDescription>
            </CardHeader>
          </Card>
        </Link>
      </div>
    </div>
  )
}
