"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { ChevronRight } from "lucide-react"
import { ClinicianPatientItem, listClinicianPatients } from "@/lib/api"

function severityVariant(band: string): "default" | "warning" | "destructive" | "secondary" {
  if (band === "sévère" || band === "modérément sévère") return "destructive"
  if (band === "modérée") return "warning"
  return "secondary"
}

export default function ClinicianPatientsPage() {
  const [patients, setPatients] = useState<ClinicianPatientItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listClinicianPatients()
      .then(setPatients)
      .catch(() => setError("Impossible de charger la liste des patients."))
  }, [])

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-5 py-8 md:px-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Patients suivis</h1>
        <p className="text-sm text-muted-foreground">
          Limité aux patients avec lesquels vous avez une relation active.
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {patients && patients.length === 0 && (
        <p className="border-y py-10 text-center text-sm text-muted-foreground">
          Aucun patient suivi pour l&apos;instant. Un administrateur doit créer la relation de suivi.
        </p>
      )}

      {patients && patients.length > 0 && (
        <div className="divide-y rounded-2xl border bg-card">
          {patients.map((p) => (
            <Link
              key={p.patient_id}
              href={`/clinician/patients/${p.patient_id}`}
              className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-accent/40"
            >
              <div className="min-w-0 space-y-1">
                <p className="truncate font-medium tracking-tight">{p.display_name || "Patient sans nom"}</p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {p.latest_phq9 ? (
                    <Badge variant={severityVariant(p.latest_phq9.severity_band)}>
                      PHQ-9 : {p.latest_phq9.severity_band}
                    </Badge>
                  ) : (
                    <Badge variant="outline">Aucun PHQ-9</Badge>
                  )}
                  {p.open_alert_count > 0 && (
                    <Badge variant="destructive">{p.open_alert_count} alerte{p.open_alert_count > 1 ? "s" : ""} ouverte{p.open_alert_count > 1 ? "s" : ""}</Badge>
                  )}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
