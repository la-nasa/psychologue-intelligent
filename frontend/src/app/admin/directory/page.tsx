"use client"

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { AdminUserItem, listAdminUsers } from "@/lib/api"

const ROLE_OPTIONS = [
  { value: "all", label: "Tous les rôles" },
  { value: "PATIENT", label: "Patients" },
  { value: "PSYCHOLOGIST", label: "Psychologues" },
  { value: "CLINICAL_SUPERVISOR", label: "Superviseurs cliniques" },
  { value: "ADMIN", label: "Administrateurs" },
  { value: "SUPER_ADMIN", label: "Super-administrateurs" },
  { value: "RESEARCHER", label: "Chercheurs" },
  { value: "ML_ENGINEER", label: "Ingénieurs ML" },
  { value: "SECURITY_AUDITOR", label: "Auditeurs sécurité" },
]

export default function AdminDirectoryPage() {
  const [role, setRole] = useState("all")
  const [users, setUsers] = useState<AdminUserItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listAdminUsers(role === "all" ? undefined : role)
      .then(setUsers)
      .catch(() => setError("Impossible de charger l'annuaire."))
  }, [role])

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Annuaire</h1>
        <p className="text-sm text-muted-foreground">Comptes de votre organisation.</p>
      </div>

      <Select value={role} onValueChange={setRole}>
        <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
        <SelectContent>
          {ROLE_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="divide-y rounded-lg border bg-card">
        {users?.length === 0 && <p className="p-6 text-sm text-muted-foreground">Aucun compte pour ce filtre.</p>}
        {users?.map((u) => (
          <div key={u.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <div>
              <p className="font-medium">{u.display_name || u.email}</p>
              <p className="text-xs text-muted-foreground">{u.email}</p>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {u.roles.map((r) => <Badge key={r} variant="outline">{r}</Badge>)}
              <Badge variant={u.status === "ACTIVE" ? "success" : "outline"}>{u.status}</Badge>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
