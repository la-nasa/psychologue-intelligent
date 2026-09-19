"use client"

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError, ChannelItem, createChannel, listChannels } from "@/lib/api"

const KIND_LABELS: Record<string, string> = { email: "E-mail", sms: "SMS", push: "Push", log: "Journal (test)" }

export default function AdminChannelsPage() {
  const [channels, setChannels] = useState<ChannelItem[] | null>(null)
  const [name, setName] = useState("")
  const [kind, setKind] = useState<"email" | "sms" | "push" | "log">("email")
  const [target, setTarget] = useState("")
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    listChannels().then(setChannels).catch(() => setError("Impossible de charger les canaux."))
  }, [])

  useEffect(() => refresh(), [refresh])

  const handleCreate = async () => {
    if (!name.trim() || !target.trim()) return
    setError(null)
    setCreating(true)
    try {
      await createChannel(name.trim(), kind, target.trim())
      setName("")
      setTarget("")
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de créer ce canal.")
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-5 py-8 md:px-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Canaux de notification</h1>
        <p className="text-sm text-muted-foreground">Destinations utilisées pour les alertes cliniques et rappels.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ajouter un canal</CardTitle>
          <CardDescription>Le contenu de la cible (adresse, numéro) reste masqué une fois enregistré.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Nom</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Astreinte clinique" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Type</label>
            <Select value={kind} onValueChange={(v) => setKind(v as typeof kind)}>
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(KIND_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Cible</label>
            <Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="astreinte@organisation.fr" />
          </div>
          <Button onClick={handleCreate} disabled={creating || !name.trim() || !target.trim()}>
            {creating ? "Ajout…" : "Ajouter"}
          </Button>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="divide-y rounded-lg border bg-card">
        {channels?.length === 0 && <p className="p-6 text-sm text-muted-foreground">Aucun canal configuré.</p>}
        {channels?.map((c) => (
          <div key={c.id} className="flex items-center justify-between gap-3 px-5 py-4">
            <div>
              <p className="font-medium">{c.name}</p>
              <p className="text-xs text-muted-foreground">{KIND_LABELS[c.kind] ?? c.kind} · {c.target_hint}</p>
            </div>
            <Badge variant={c.is_active ? "success" : "outline"}>{c.is_active ? "Actif" : "Inactif"}</Badge>
          </div>
        ))}
      </div>
    </div>
  )
}
