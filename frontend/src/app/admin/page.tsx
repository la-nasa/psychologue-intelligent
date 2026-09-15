"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Link2Off } from "lucide-react"
import {
  AdminUserItem,
  ApiError,
  RelationshipItem,
  createRelationship,
  endRelationship,
  listAdminUsers,
  listRelationships,
} from "@/lib/api"

function userLabel(user: AdminUserItem | undefined, id: string): string {
  if (!user) return id.slice(0, 8)
  return user.display_name ? `${user.display_name} (${user.email})` : user.email
}

export default function AdminRelationshipsPage() {
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [relationships, setRelationships] = useState<RelationshipItem[] | null>(null)
  const [patientId, setPatientId] = useState<string | undefined>()
  const [clinicianId, setClinicianId] = useState<string | undefined>()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    listRelationships()
      .then(setRelationships)
      .catch(() => setError("Impossible de charger les relations."))
  }, [])

  useEffect(() => {
    listAdminUsers()
      .then(setUsers)
      .catch(() => setError("Impossible de charger l'annuaire."))
    refresh()
  }, [refresh])

  const usersById = useMemo(() => new Map(users.map((u) => [u.id, u])), [users])
  const patients = useMemo(() => users.filter((u) => u.roles.includes("PATIENT")), [users])
  const clinicians = useMemo(
    () => users.filter((u) => u.roles.includes("PSYCHOLOGIST") || u.roles.includes("CLINICAL_SUPERVISOR")),
    [users],
  )

  const handleCreate = async () => {
    if (!patientId || !clinicianId) return
    setError(null)
    setCreating(true)
    try {
      await createRelationship(patientId, clinicianId)
      setPatientId(undefined)
      setClinicianId(undefined)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de créer cette relation.")
    } finally {
      setCreating(false)
    }
  }

  const handleEnd = async (relationshipId: string) => {
    try {
      await endRelationship(relationshipId)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de terminer cette relation.")
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Relations patient-clinicien</h1>
        <p className="text-sm text-muted-foreground">
          Seule porte d&apos;accès d&apos;un clinicien au dossier d&apos;un patient.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Créer une relation</CardTitle>
          <CardDescription>Le patient et le clinicien doivent déjà avoir un compte.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Patient</label>
            <Select value={patientId} onValueChange={setPatientId}>
              <SelectTrigger><SelectValue placeholder="Choisir un patient" /></SelectTrigger>
              <SelectContent>
                {patients.map((p) => <SelectItem key={p.id} value={p.id}>{userLabel(p, p.id)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Clinicien</label>
            <Select value={clinicianId} onValueChange={setClinicianId}>
              <SelectTrigger><SelectValue placeholder="Choisir un clinicien" /></SelectTrigger>
              <SelectContent>
                {clinicians.map((c) => <SelectItem key={c.id} value={c.id}>{userLabel(c, c.id)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handleCreate} disabled={!patientId || !clinicianId || creating}>
            {creating ? "Création…" : "Créer"}
          </Button>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="divide-y rounded-lg border bg-card">
        {relationships?.length === 0 && (
          <p className="p-6 text-sm text-muted-foreground">Aucune relation créée pour l&apos;instant.</p>
        )}
        {relationships?.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <div className="space-y-1 text-sm">
              <p>
                <span className="font-medium">{userLabel(usersById.get(r.patient_id), r.patient_id)}</span>
                {" "}suivi par{" "}
                <span className="font-medium">{userLabel(usersById.get(r.clinician_id), r.clinician_id)}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                Depuis le {new Date(r.created_at).toLocaleDateString("fr-FR")}
                {r.ended_at && ` — terminée le ${new Date(r.ended_at).toLocaleDateString("fr-FR")}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={r.status === "ACTIVE" ? "success" : "outline"}>{r.status}</Badge>
              {r.status === "ACTIVE" && (
                <Button size="sm" variant="outline" onClick={() => handleEnd(r.id)}>
                  <Link2Off className="h-3.5 w-3.5" strokeWidth={1.75} /> Terminer
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
