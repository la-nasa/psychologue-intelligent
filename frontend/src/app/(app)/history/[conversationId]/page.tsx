"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ArrowLeft, Search } from "lucide-react"
import { ApiError, MessageItem, listMessages } from "@/lib/api"

export default function ConversationDetailPage() {
  const params = useParams<{ conversationId: string }>()
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState("")

  useEffect(() => {
    listMessages(params.conversationId)
      .then(setMessages)
      .catch((err) => {
        setError(
          err instanceof ApiError && err.status === 404
            ? "Cette conversation n'existe pas ou ne vous appartient pas."
            : "Impossible de charger cette conversation.",
        )
      })
      .finally(() => setLoading(false))
  }, [params.conversationId])

  const filtered = messages.filter((m) => m.content.toLowerCase().includes(searchTerm.toLowerCase()))

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="space-y-4 px-6 pb-4 pt-8 md:pt-10">
        <Link href="/history" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} /> Retour à l&apos;historique
        </Link>
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
          <div className="space-y-3">
            <p className="text-sm text-destructive">{error}</p>
            <Button asChild size="sm" variant="outline">
              <Link href="/history">Retour à l&apos;historique</Link>
            </Button>
          </div>
        ) : (
          <div className="divide-y">
            {filtered.map((m) => (
              <div key={m.id} className="flex gap-4 py-4">
                <Badge variant={m.author_type === "PATIENT" ? "secondary" : "outline"} className="h-fit shrink-0">
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
