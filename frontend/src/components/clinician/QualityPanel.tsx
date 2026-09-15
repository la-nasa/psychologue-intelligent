"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ShieldAlert } from "lucide-react"
import { QualityReport, SafetyFlagItem, getQualityReport, getSafetyFlags } from "@/lib/api"

const DIMENSION_LABELS: Record<string, string> = {
  empathy: "Empathie",
  relevance: "Pertinence",
  personalization: "Personnalisation",
  context: "Contexte",
  safety: "Sûreté",
  clarity: "Clarté",
  usefulness: "Utilité",
}

/**
 * Rapport qualité agrégé strictement par version de modèle (gouvernance non
 * punitive — aucun identifiant de relecteur n'apparaît nulle part ici) et
 * signalements de sûreté. Partagé entre l'espace clinicien (superviseur) et
 * la console admin (super-admin) — mêmes endpoints, même contrat oversight.
 */
export function QualityPanel() {
  const [report, setReport] = useState<QualityReport | null>(null)
  const [flags, setFlags] = useState<SafetyFlagItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getQualityReport(), getSafetyFlags()])
      .then(([r, f]) => {
        setReport(r)
        setFlags(f)
      })
      .catch(() => setError("Impossible de charger le rapport qualité."))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!report) return null

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Toutes versions de modèle</CardTitle>
          <CardDescription>{report.review_count} revue{report.review_count !== 1 ? "s" : ""} au total.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(report.by_decision).map(([decision, count]) => (
              <div key={decision} className="rounded-md border p-3 text-center">
                <p className="text-lg font-semibold tabular-nums">{count}</p>
                <p className="text-xs text-muted-foreground">{decision}</p>
              </div>
            ))}
          </div>
          {report.approval_rate != null && (
            <p className="text-sm">
              Taux d&apos;approbation : <span className="font-medium tabular-nums">{Math.round(report.approval_rate * 100)}%</span>
            </p>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(report.mean_scores).map(([dim, value]) => (
              <div key={dim} className="space-y-1">
                <p className="text-xs text-muted-foreground">{DIMENSION_LABELS[dim] ?? dim}</p>
                <p className="text-sm font-medium tabular-nums">{value != null ? value.toFixed(2) : "—"} / 5</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <h2 className="flex items-center gap-2 text-base font-medium tracking-tight">
          <ShieldAlert className="h-4 w-4 text-destructive" strokeWidth={1.75} />
          Signalements de sûreté
        </h2>
        {flags?.length === 0 && <p className="text-sm text-muted-foreground">Aucun signalement.</p>}
        {flags?.map((f) => (
          <Card key={f.id}>
            <CardContent className="space-y-1 p-4">
              <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">{f.feedback_category}</Badge>
                <span>{new Date(f.created_at).toLocaleString("fr-FR")}</span>
              </div>
              {f.clinical_comment && <p className="text-sm">{f.clinical_comment}</p>}
              {f.model_version && <p className="text-xs text-muted-foreground">Modèle : {f.model_version}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
