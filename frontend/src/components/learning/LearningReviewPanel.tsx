"use client"

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Check, X, Rocket, Undo2 } from "lucide-react"
import {
  ApiError,
  LearningSample,
  listLearningSamples,
  promoteLearningSample,
  reviewLearningSample,
  rollbackLearningSample,
} from "@/lib/api"

const STATUS_VARIANT: Record<LearningSample["status"], "outline" | "success" | "destructive" | "warning"> = {
  PENDING_REVIEW: "outline",
  APPROVED: "success",
  REJECTED: "destructive",
  PROMOTED: "success",
  ROLLED_BACK: "warning",
}

const STATUS_LABEL: Record<LearningSample["status"], string> = {
  PENDING_REVIEW: "En attente de revue",
  APPROVED: "Doublement approuvé",
  REJECTED: "Rejeté",
  PROMOTED: "Promu",
  ROLLED_BACK: "Annulé",
}

function DecisionBadge({ label, decision }: { label: string; decision: "APPROVE" | "REJECT" | null }) {
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      {label} :
      {decision === null ? (
        <span className="text-muted-foreground">en attente</span>
      ) : decision === "APPROVE" ? (
        <span className="flex items-center gap-0.5 text-success"><Check className="h-3 w-3" strokeWidth={2} /> approuvé</span>
      ) : (
        <span className="flex items-center gap-0.5 text-destructive"><X className="h-3 w-3" strokeWidth={2} /> rejeté</span>
      )}
    </span>
  )
}

/**
 * File de revue de l'apprentissage continu (Phase 16). Partagée entre l'espace
 * clinicien (revue clinique) et l'espace ML (revue technique + promotion) —
 * le backend attribue automatiquement la décision au bon créneau selon le
 * rôle de l'appelant. Rien ici ne déclenche un ré-entraînement : la promotion
 * marque seulement l'échantillon comme retenu pour un futur jeu de données,
 * en dehors du périmètre technique de cette plateforme.
 */
export function LearningReviewPanel({ canPromote }: { canPromote: boolean }) {
  const [samples, setSamples] = useState<LearningSample[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [rollbackReason, setRollbackReason] = useState<Record<string, string>>({})

  const refresh = useCallback(() => {
    listLearningSamples()
      .then(setSamples)
      .catch(() => setError("Impossible de charger la file de revue."))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const act = async (fn: () => Promise<unknown>, id: string) => {
    setBusyId(id)
    setError(null)
    try {
      await fn()
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action impossible.")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-destructive">{error}</p>}
      {samples?.length === 0 && (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">Aucun échantillon pour l&apos;instant.</CardContent></Card>
      )}
      {samples?.map((s) => (
        <Card key={s.id}>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge variant={STATUS_VARIANT[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                {s.model_version && <span>{s.model_version}</span>}
                <span>{new Date(s.created_at).toLocaleString("fr-FR")}</span>
              </div>
              <div className="flex items-center gap-3">
                <DecisionBadge label="Clinique" decision={s.clinical_decision} />
                <DecisionBadge label="Technique" decision={s.technical_decision} />
              </div>
            </div>

            {s.anonymized_prompt && (
              <p className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Patient (anonymisé) : </span>{s.anonymized_prompt}
              </p>
            )}
            <p className="rounded-md border p-3 text-sm">
              <span className="font-medium">Assistant (anonymisé) : </span>{s.anonymized_response}
            </p>

            {s.status === "PENDING_REVIEW" && (
              <div className="flex flex-wrap gap-2 border-t pt-3">
                <Button size="sm" disabled={busyId === s.id} onClick={() => act(() => reviewLearningSample(s.id, "APPROVE"), s.id)}>
                  <Check className="h-3.5 w-3.5" strokeWidth={1.75} /> Approuver
                </Button>
                <Button size="sm" variant="outline" disabled={busyId === s.id} onClick={() => act(() => reviewLearningSample(s.id, "REJECT"), s.id)}>
                  <X className="h-3.5 w-3.5" strokeWidth={1.75} /> Rejeter
                </Button>
              </div>
            )}

            {canPromote && s.status === "APPROVED" && (
              <div className="flex flex-wrap gap-2 border-t pt-3">
                <Button size="sm" disabled={busyId === s.id} onClick={() => act(() => promoteLearningSample(s.id), s.id)}>
                  <Rocket className="h-3.5 w-3.5" strokeWidth={1.75} /> Promouvoir
                </Button>
              </div>
            )}

            {canPromote && s.status === "PROMOTED" && (
              <div className="space-y-2 border-t pt-3">
                <Textarea
                  placeholder="Motif de l'annulation"
                  value={rollbackReason[s.id] ?? ""}
                  onChange={(e) => setRollbackReason((prev) => ({ ...prev, [s.id]: e.target.value }))}
                  className="min-h-16 text-sm"
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId === s.id || !(rollbackReason[s.id] ?? "").trim()}
                  onClick={() => act(() => rollbackLearningSample(s.id, rollbackReason[s.id] ?? ""), s.id)}
                >
                  <Undo2 className="h-3.5 w-3.5" strokeWidth={1.75} /> Annuler la promotion
                </Button>
              </div>
            )}

            {s.status === "ROLLED_BACK" && s.rollback_reason && (
              <p className="border-t pt-3 text-xs text-muted-foreground">Motif : {s.rollback_reason}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
