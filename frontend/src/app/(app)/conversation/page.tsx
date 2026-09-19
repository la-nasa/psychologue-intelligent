"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Send, SquarePen } from "lucide-react"
import {
  ApiError,
  clearToken,
  getToken,
  listMessages,
  startConversation,
  startNewConversation,
  streamMessage,
} from "@/lib/api"
import { EMERGENCY_BANNER } from "@/lib/emergency"
import { AuthGate, PageSkeleton } from "@/components/layout/EmptyState"

const WELCOME_MESSAGE =
  "Bonjour. Nous avons un moment pour parler de ce qui vous préoccupe. Par quoi souhaitez-vous commencer aujourd'hui ?"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  decisionLevel?: string
  generationPath?: string
}

type AuthState = "checking" | "authenticated" | "anonymous"

export default function ConversationPage() {
  const [authState, setAuthState] = useState<AuthState>("checking")
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [setupError, setSetupError] = useState<string | null>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const [startingNew, setStartingNew] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const streamAbort = useRef<AbortController | null>(null)

  const hydrate = (convoId: string) => {
    setConversationId(convoId)
    listMessages(convoId)
      .then((items) => {
        if (items.length === 0) {
          setMessages([{ id: "welcome", role: "assistant", content: WELCOME_MESSAGE, timestamp: new Date() }])
          return
        }
        setMessages(
          items.map((m) => ({
            id: m.id,
            role: m.author_type === "PATIENT" ? "user" : "assistant",
            content: m.content,
            timestamp: new Date(m.created_at),
          })),
        )
      })
      .catch(() => {
        // L'historique n'a pas pu être rechargé : on n'empêche pas de continuer à écrire.
        setMessages([{ id: "welcome", role: "assistant", content: WELCOME_MESSAGE, timestamp: new Date() }])
      })
  }

  useEffect(() => {
    if (!getToken()) {
      setAuthState("anonymous")
      return
    }
    setAuthState("authenticated")
    startConversation()
      .then((convo) => hydrate(convo.id))
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

  const handleNewConversation = async () => {
    if (startingNew) return
    setStartingNew(true)
    streamAbort.current?.abort()
    try {
      const convo = await startNewConversation()
      setConversationId(convo.id)
      setMessages([{ id: "welcome", role: "assistant", content: WELCOME_MESSAGE, timestamp: new Date() }])
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        setAuthState("anonymous")
      } else {
        setSetupError("Impossible de démarrer une nouvelle conversation.")
      }
    } finally {
      setStartingNew(false)
    }
  }

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
                m.id === assistantId
                  ? {
                      ...m,
                      content: event.content,
                      decisionLevel: event.decision_level,
                      generationPath: event.generation_path,
                    }
                  : m,
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
    return <PageSkeleton lines={3} />
  }

  if (authState === "anonymous") {
    return <AuthGate message="Connectez-vous pour discuter avec l'assistant." />
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col pb-16 md:pb-0">
      {setupError && (
        <p className="border-b bg-destructive/10 p-2 text-center text-sm text-destructive">{setupError}</p>
      )}

      <div className="flex items-center justify-end px-4 pt-3 md:px-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleNewConversation}
          disabled={startingNew || isStreaming}
          className="text-muted-foreground hover:text-foreground"
        >
          <SquarePen className="h-3.5 w-3.5" strokeWidth={1.5} />
          Nouvelle conversation
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-6" ref={scrollRef}>
        <div className="space-y-6">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={
                  message.role === "user"
                    ? "max-w-[78%] rounded-2xl bg-primary px-4 py-2.5 text-[15px] leading-relaxed text-primary-foreground"
                    : "max-w-[min(65ch,100%)] text-[15px] leading-[1.65]"
                }
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                <p
                  className={`mt-1.5 font-mono text-[11px] tabular-nums ${
                    message.role === "user" ? "text-primary-foreground/55" : "text-muted-foreground"
                  }`}
                >
                  {message.timestamp.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                  {message.role === "assistant" &&
                    (message.decisionLevel === "RED" ||
                      message.decisionLevel === "ORANGE" ||
                      message.generationPath === "TEMPLATE") && (
                      <span className="ml-2 font-sans font-medium">· consigne de sécurité</span>
                    )}
                </p>
              </div>
            </div>
          ))}
          {isStreaming && messages[messages.length - 1]?.content === "" && (
            <div className="flex justify-start" aria-live="polite">
              <div className="flex gap-1.5 py-2">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:0.3s]" />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="border-t bg-background/80 px-4 py-3 backdrop-blur-sm md:px-6">
        <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-soft focus-within:border-primary/35">
          <Textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ce qui compte pour vous…"
            disabled={!conversationId || isStreaming}
            rows={1}
            className="min-h-[44px] max-h-40 resize-none border-0 py-2.5 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          <Button
            onClick={handleSend}
            size="icon"
            className="mb-0.5 h-10 w-10 shrink-0"
            disabled={!conversationId || isStreaming || !inputValue.trim()}
            aria-label="Envoyer"
          >
            <Send className="h-4 w-4" strokeWidth={1.5} />
          </Button>
        </div>
        <p className="mt-2 px-1 text-center text-xs leading-relaxed text-muted-foreground">{EMERGENCY_BANNER}</p>
      </div>
    </div>
  )
}
