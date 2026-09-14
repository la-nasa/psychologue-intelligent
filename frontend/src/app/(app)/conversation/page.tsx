"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Send } from "lucide-react"
import { ApiError, clearToken, getToken, startConversation, streamMessage } from "@/lib/api"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  decisionLevel?: string
}

type AuthState = "checking" | "authenticated" | "anonymous"

export default function ConversationPage() {
  const [authState, setAuthState] = useState<AuthState>("checking")
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [setupError, setSetupError] = useState<string | null>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const streamAbort = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!getToken()) {
      setAuthState("anonymous")
      return
    }
    setAuthState("authenticated")
    startConversation()
      .then((convo) => {
        setConversationId(convo.id)
        setMessages([
          {
            id: "welcome",
            role: "assistant",
            content: "Bonjour. Comment vous sentez-vous aujourd'hui ? Je suis là pour vous écouter.",
            timestamp: new Date(),
          },
        ])
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          setAuthState("anonymous")
        } else {
          setSetupError("Impossible de démarrer la conversation. Le serveur est-il démarré ?")
        }
      })

    return () => streamAbort.current?.abort()
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  const handleSend = async () => {
    const text = inputValue.trim()
    if (!text || !conversationId || isStreaming) return

    const userMessage: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    }
    const assistantId = `local-${Date.now() + 1}`
    setMessages((prev) => [...prev, userMessage, { id: assistantId, role: "assistant", content: "", timestamp: new Date() }])
    setInputValue("")
    setIsStreaming(true)

    const controller = new AbortController()
    streamAbort.current = controller

    try {
      await streamMessage(
        conversationId,
        text,
        (event) => {
          if (event.type === "assistant_chunk") {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + event.text } : m)),
            )
          } else if (event.type === "assistant_correction") {
            setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content: event.text } : m)))
          } else if (event.type === "assistant_message") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: event.content, decisionLevel: event.decision_level } : m,
              ),
            )
          }
        },
        controller.signal,
      )
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        setAuthState("anonymous")
      } else if (!(err instanceof DOMException && err.name === "AbortError")) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: "Une erreur est survenue, veuillez réessayer." } : m,
          ),
        )
      }
    } finally {
      setIsStreaming(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (authState === "checking") {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Chargement…</div>
  }

  if (authState === "anonymous") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour discuter avec votre assistant.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col">
      {setupError && (
        <p className="border-b bg-destructive/10 p-2 text-center text-sm text-destructive">{setupError}</p>
      )}

      <ScrollArea className="flex-1 px-4 py-6 md:px-0" ref={scrollRef}>
        <div className="space-y-5">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "border bg-card"
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                <p
                  className={`mt-1 text-[11px] tabular-nums ${
                    message.role === "user" ? "text-primary-foreground/60" : "text-muted-foreground"
                  }`}
                >
                  {message.timestamp.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
            </div>
          ))}
          {isStreaming && (
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-xl border bg-card px-4 py-3">
                <div className="flex gap-1.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:0.3s]" />
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t px-4 py-4 md:px-0">
        <div className="flex items-center gap-2 rounded-xl border bg-card p-1.5 shadow-soft transition-colors focus-within:border-primary/40">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Écrivez ce que vous ressentez…"
            disabled={!conversationId || isStreaming}
            className="border-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          <Button
            onClick={handleSend}
            size="icon"
            disabled={!conversationId || isStreaming || !inputValue.trim()}
            aria-label="Envoyer"
          >
            <Send className="h-4 w-4" strokeWidth={1.75} />
          </Button>
        </div>
        <p className="mt-2 px-1 text-center text-xs text-muted-foreground">
          Cet espace est confidentiel. En cas d&apos;urgence, contactez les secours (15, 112) ou le 3114.
        </p>
      </div>
    </div>
  )
}
