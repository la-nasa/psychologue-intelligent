"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { History, ChevronRight } from "lucide-react"
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
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour voir votre historique.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Historique</h1>
        <p className="text-sm text-muted-foreground">Toutes vos conversations, de la plus récente à la plus ancienne.</p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : conversations.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center">
          <History className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">Aucune conversation pour le moment.</p>
        </div>
      ) : (
        <div className="divide-y rounded-lg border bg-card">
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
    </div>
  )
}
