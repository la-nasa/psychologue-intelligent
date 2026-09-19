"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { PageShell, PageHeader } from "@/components/layout/PageShell"
import { PageSkeleton } from "@/components/layout/EmptyState"
import { StatStrip } from "@/components/layout/StatStrip"
import { ClinicianOverview, getClinicianOverview } from "@/lib/api"

export default function ClinicianOverviewPage() {
  const [overview, setOverview] = useState<ClinicianOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getClinicianOverview()
      .then(setOverview)
      .catch(() => setError("Impossible de charger la vue d'ensemble."))
  }, [])

  return (
    <PageShell wide>
      <PageHeader title="Vue d'ensemble" description="Votre file de travail du jour." />

      {error && <p className="text-sm text-destructive">{error}</p>}
      {!overview && !error && <PageSkeleton lines={2} />}

      {overview && (
        <StatStrip
          items={[
            { label: "Patients suivis", value: overview.patients_followed },
            {
              label: "Alertes rouges",
              value: overview.open_alerts.red,
              tone: overview.open_alerts.red > 0 ? "danger" : "default",
            },
            {
              label: "Alertes orange",
              value: overview.open_alerts.orange,
              tone: overview.open_alerts.orange > 0 ? "warning" : "default",
            },
            {
              label: "SLA dépassés",
              value: overview.sla_breached,
              tone: overview.sla_breached > 0 ? "danger" : "default",
            },
          ]}
        />
      )}

      <div className="divide-y border-y">
        <Link href="/clinician/alerts" className="group flex min-h-16 items-center justify-between gap-4 py-4">
          <div>
            <p className="font-medium tracking-tight">Centre d&apos;alertes</p>
            <p className="text-sm text-muted-foreground">ORANGE / RED, SLA et cycle de vie.</p>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" strokeWidth={1.5} />
        </Link>
        <Link href="/clinician/patients" className="group flex min-h-16 items-center justify-between gap-4 py-4">
          <div>
            <p className="font-medium tracking-tight">Patients suivis</p>
            <p className="text-sm text-muted-foreground">Dossier, PHQ-9, synthèse corrélationnelle.</p>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" strokeWidth={1.5} />
        </Link>
        <Link href="/clinician/review" className="group flex min-h-16 items-center justify-between gap-4 py-4">
          <div>
            <p className="font-medium tracking-tight">Revue des réponses IA</p>
            <p className="text-sm text-muted-foreground">Approuver, corriger ou signaler.</p>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" strokeWidth={1.5} />
        </Link>
      </div>
    </PageShell>
  )
}
