"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MessageCircle, Search } from "lucide-react"
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
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <h2 className="text-2xl font-bold tracking-tight">Historique</h2>
        <p className="text-muted-foreground">
          Messages de votre conversation en cours. Le découpage par session avec résumé et humeur (vu dans les
          premières maquettes de cette page) n&apos;existe pas encore côté serveur — une seule conversation active
          par patient est modélisée pour l&apos;instant.
        </p>
      </div>

      {/* Filters */}
      <div className="border-b p-4">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Rechercher dans les messages..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucun message pour le moment.</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((m) => (
              <Card key={m.id}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 py-3">
                  <div className="flex items-center gap-2">
                    <MessageCircle className="h-4 w-4 text-muted-foreground" />
                    <Badge variant={m.author_type === "PATIENT" ? "secondary" : "outline"}>
                      {m.author_type === "PATIENT" ? "Vous" : "Assistant"}
                    </Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(m.created_at).toLocaleString("fr-FR")}
                  </span>
                </CardHeader>
                <CardContent className="pt-0">
                  <p className="text-sm whitespace-pre-wrap">{m.content}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
