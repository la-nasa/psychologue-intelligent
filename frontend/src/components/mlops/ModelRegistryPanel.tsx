"use client"

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ExternalLink, Undo2 } from "lucide-react"
import {
  ApiError,
  ModelStage,
  ModelVersionItem,
  listModelVersions,
  promoteModelVersion,
  registerModelVersion,
  rollbackModelVersion,
} from "@/lib/api"

const STAGE_ORDER: ModelStage[] = ["EXPERIMENTAL", "STAGING", "SHADOW", "CANARY", "PRODUCTION", "RETIRED"]
const NEXT_STAGE: Partial<Record<ModelStage, ModelStage[]>> = {
  EXPERIMENTAL: ["STAGING", "RETIRED"],
  STAGING: ["SHADOW", "RETIRED"],
  SHADOW: ["CANARY", "RETIRED"],
  CANARY: ["PRODUCTION", "RETIRED"],
  PRODUCTION: ["RETIRED"],
}

const STAGE_VARIANT: Record<ModelStage, "outline" | "warning" | "success" | "secondary"> = {
  EXPERIMENTAL: "outline",
  STAGING: "warning",
  SHADOW: "warning",
  CANARY: "warning",
  PRODUCTION: "success",
  RETIRED: "secondary",
}

/**
 * Registre de versions de modèle (Phase 17, ADR-011) — la table `model_versions`
 * locale reste la source de vérité de gouvernance ; le lien MLflow (badge
 * "MLflow" ci-dessous) est un miroir best-effort pour la traçabilité externe,
 * jamais un pré-requis pour agir ici.
 */
export function ModelRegistryPanel() {
  const [versions, setVersions] = useState<ModelVersionItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [rollbackReason, setRollbackReason] = useState<Record<string, string>>({})
  const [targetStage, setTargetStage] = useState<Record<string, ModelStage>>({})

  const [name, setName] = useState("")
  const [version, setVersion] = useState("")
  const [notes, setNotes] = useState("")
  const [registering, setRegistering] = useState(false)

  const refresh = useCallback(() => {
    listModelVersions()
      .then(setVersions)
      .catch(() => setError("Impossible de charger le registre de modèles."))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleRegister = async () => {
    if (!name.trim() || !version.trim()) return
    setRegistering(true)
    setError(null)
    try {
      await registerModelVersion(name.trim(), version.trim(), notes.trim())
      setName("")
      setVersion("")
      setNotes("")
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'enregistrer cette version.")
    } finally {
      setRegistering(false)
    }
  }

  const handlePromote = async (id: string) => {
    const stage = targetStage[id]
    if (!stage) return
    setBusyId(id)
    setError(null)
    try {
      await promoteModelVersion(id, stage)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Transition impossible.")
    } finally {
      setBusyId(null)
    }
  }

  const handleRollback = async (id: string) => {
    const reason = (rollbackReason[id] ?? "").trim()
    if (!reason) return
    setBusyId(id)
    setError(null)
    try {
      await rollbackModelVersion(id, reason)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Annulation impossible.")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Enregistrer une version</CardTitle>
          <CardDescription>
            Enregistre une version déjà produite (moteur à règles, gabarit) — n&apos;entraîne rien.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <Input placeholder="Nom (ex. local-supportive)" value={name} onChange={(e) => setName(e.target.value)} />
            <Input placeholder="Version (ex. dev-1)" value={version} onChange={(e) => setVersion(e.target.value)} />
          </div>
          <Textarea placeholder="Notes / fiche modèle" value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-16 text-sm" />
          <Button size="sm" onClick={handleRegister} disabled={registering || !name.trim() || !version.trim()}>
            {registering ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="space-y-3">
        {versions?.length === 0 && (
          <Card><CardContent className="p-6 text-sm text-muted-foreground">Aucune version enregistrée.</CardContent></Card>
        )}
        {versions?.map((v) => {
          const options = NEXT_STAGE[v.stage] ?? []
          return (
            <Card key={v.id}>
              <CardContent className="space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium tracking-tight">{v.name}</span>
                    <span className="text-sm text-muted-foreground">v{v.version}</span>
                    <Badge variant={STAGE_VARIANT[v.stage]}>{v.stage}</Badge>
                    {v.mlflow_linked ? (
                      <Badge variant="outline" className="flex items-center gap-1">
                        <ExternalLink className="h-3 w-3" strokeWidth={1.75} /> MLflow
                      </Badge>
                    ) : (
                      <Badge variant="outline">Local uniquement</Badge>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(v.updated_at).toLocaleString("fr-FR")}
                  </span>
                </div>
                {v.notes && <p className="whitespace-pre-wrap text-sm text-muted-foreground">{v.notes}</p>}

                {options.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 border-t pt-3">
                    <Select value={targetStage[v.id]} onValueChange={(val) => setTargetStage((prev) => ({ ...prev, [v.id]: val as ModelStage }))}>
                      <SelectTrigger className="w-44"><SelectValue placeholder="Étape cible" /></SelectTrigger>
                      <SelectContent>
                        {options.map((stage) => <SelectItem key={stage} value={stage}>{stage}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <Button size="sm" disabled={busyId === v.id || !targetStage[v.id]} onClick={() => handlePromote(v.id)}>
                      Transitionner
                    </Button>
                  </div>
                )}

                {(v.stage === "CANARY" || v.stage === "PRODUCTION") && (
                  <div className="space-y-2 border-t pt-3">
                    <Textarea
                      placeholder="Motif de l'annulation"
                      value={rollbackReason[v.id] ?? ""}
                      onChange={(e) => setRollbackReason((prev) => ({ ...prev, [v.id]: e.target.value }))}
                      className="min-h-16 text-sm"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyId === v.id || !(rollbackReason[v.id] ?? "").trim()}
                      onClick={() => handleRollback(v.id)}
                    >
                      <Undo2 className="h-3.5 w-3.5" strokeWidth={1.75} /> Retirer (rollback)
                    </Button>
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
