"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { History, Search } from "lucide-react"
import { ApiError, clearToken, getToken, listMessages, MessageItem, startConversation } from "@/lib/api"

export default function HistoryPage() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState("")

  useEffect(() => {
    if (!getToken()) {
      setAuthed(false)
      return
    }
    setAuthed(true)
    startConversation()
      .then((convo) => listMessages(convo.id))
      .then((items) => setMessages(items))
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

  const filtered = messages.filter((m) => m.content.toLowerCase().includes(searchTerm.toLowerCase()))

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="space-y-4 px-6 pb-4 pt-8 md:pt-10">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Historique</h1>
          <p className="text-sm text-muted-foreground">
            Messages de votre conversation en cours. Le regroupement par session arrivera avec une prochaine mise à
            jour — une seule conversation active est suivie pour l&apos;instant.
          </p>
        </div>
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" strokeWidth={1.75} />
          <Input
            placeholder="Rechercher dans les messages…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <ScrollArea className="flex-1 px-6 pb-8">
        {loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : filtered.length === 0 ? (
          <div className="rounded-lg border border-dashed p-10 text-center">
            <History className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">Aucun message pour le moment.</p>
          </div>
        ) : (
          <div className="divide-y">
            {filtered.map((m) => (
              <div key={m.id} className="flex gap-4 py-4">
                <Badge
                  variant={m.author_type === "PATIENT" ? "secondary" : "outline"}
                  className="h-fit shrink-0"
                >
                  {m.author_type === "PATIENT" ? "Vous" : "Assistant"}
                </Badge>
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(m.created_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
