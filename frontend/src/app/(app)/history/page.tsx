"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { History, ChevronRight } from "lucide-react"
import { PageShell, PageHeader } from "@/components/layout/PageShell"
import { AuthGate, EmptyState, PageSkeleton } from "@/components/layout/EmptyState"
import { ApiError, clearToken, ConversationSummary, getToken, listConversations } from "@/lib/api"

export default function HistoryPage() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!getToken()) {
      setAuthed(false)
      return
    }
    setAuthed(true)
    listConversations()
      .then(setConversations)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          setAuthed(false)
        } else {
          setError("Impossible de charger l'historique.")
        }
      })
      .finally(() => setLoading(false))
  }, [])

  if (authed === false) {
    return <AuthGate message="Connectez-vous pour voir votre historique." />
  }

  return (
    <PageShell>
      <PageHeader
        title="Historique"
        description="Toutes vos conversations, de la plus récente à la plus ancienne."
      />

      {loading ? (
        <PageSkeleton lines={4} />
      ) : error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : conversations.length === 0 ? (
        <EmptyState icon={History} title="Aucune conversation" description="Vos entretiens apparaîtront ici." actionHref="/conversation" actionLabel="Commencer" />
      ) : (
        <div className="divide-y rounded-2xl border bg-card">
          {conversations.map((c) => (
            <Link
              key={c.id}
              href={`/history/${c.id}`}
              className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-accent/40"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium tracking-tight">
                    {new Date(c.created_at).toLocaleDateString("fr-FR", { dateStyle: "long" })}
                  </span>
                  <Badge variant={c.status === "ACTIVE" ? "success" : "outline"}>
                    {c.status === "ACTIVE" ? "En cours" : "Terminée"}
                  </Badge>
                </div>
                <p className="truncate text-sm text-muted-foreground">
                  {c.last_message
                    ? `${c.last_message.author_type === "PATIENT" ? "Vous : " : "Assistant : "}${c.last_message.text}`
                    : "Aucun message."}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="text-xs tabular-nums text-muted-foreground">
                  {c.message_count} message{c.message_count > 1 ? "s" : ""}
                </span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </PageShell>
  )
}
