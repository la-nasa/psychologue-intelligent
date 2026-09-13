"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Send, Mic, StopCircle, Paperclip } from "lucide-react"
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
  const [isRecording, setIsRecording] = useState(false)
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
            content: "Bonjour ! Comment vous sentez-vous aujourd'hui ? Je suis là pour vous écouter.",
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

  const toggleRecording = () => {
    setIsRecording(!isRecording)
    // Capture micro réelle : hors périmètre de ce câblage (voir ADR-013, Phase 11 non commencée).
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // onKeyPress est déprécié et ne se déclenche plus de façon fiable pour
    // Enter dans certains navigateurs/automations — onKeyDown est l'équivalent
    // moderne (trouvé en testant le déploiement réel, 2026-09-13).
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
        <p className="text-sm text-muted-foreground">Connectez-vous pour discuter avec l&apos;assistant.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Conversation</h2>
            <p className="text-sm text-muted-foreground">Session en cours</p>
          </div>
          <Badge variant="secondary">Texte</Badge>
        </div>
      </div>

      {setupError && (
        <p className="border-b bg-destructive/10 p-2 text-center text-sm text-destructive">{setupError}</p>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg p-3 ${
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                <p className="mt-1 text-xs opacity-70">
                  {message.timestamp.toLocaleTimeString("fr-FR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </div>
          ))}
          {isStreaming && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg bg-muted p-3">
                <div className="flex space-x-2">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "0.2s" }} />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "0.4s" }} />
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-4">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={toggleRecording}
            className={isRecording ? "text-red-600" : ""}
          >
            {isRecording ? <StopCircle className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </Button>
          <Button variant="outline" size="icon">
            <Paperclip className="h-5 w-5" />
          </Button>
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Écrivez votre message..."
            className="flex-1"
            disabled={!conversationId || isStreaming}
          />
          <Button onClick={handleSend} size="icon" disabled={!conversationId || isStreaming}>
            <Send className="h-5 w-5" />
          </Button>
        </div>
        {isRecording && (
          <p className="mt-2 text-center text-sm text-muted-foreground">Enregistrement en cours...</p>
        )}
      </div>
    </div>
  )
}
