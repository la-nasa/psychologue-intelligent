"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Mic, MicOff, MessageCircle, Volume2, VolumeX } from "lucide-react"
import {
  ApiError,
  clearToken,
  getToken,
  grantConsent,
  listConsents,
  startConversation,
  streamMessage,
} from "@/lib/api"

interface VoiceTurn {
  id: string
  role: "user" | "assistant"
  content: string
}

type SetupState = "checking" | "anonymous" | "unsupported" | "consent_needed" | "ready"

// Le SDK TS ne connaît pas le Web Speech API — types minimaux pour ce qu'on utilise.
interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: { transcript: string }
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>
  resultIndex: number
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
}

function getSpeechRecognition(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as Record<string, unknown>
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => SpeechRecognitionLike) | null
}

export default function VoicePage() {
  const [state, setState] = useState<SetupState>("checking")
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [turns, setTurns] = useState<VoiceTurn[]>([])
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState("")
  const [muted, setMuted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  useEffect(() => {
    if (!getToken()) {
      setState("anonymous")
      return
    }
    if (!getSpeechRecognition()) {
      setState("unsupported")
      return
    }
    listConsents()
      .then((consents) => {
        const active = consents.find((c) => c.purpose === "VOICE")?.active ?? false
        setState(active ? "ready" : "consent_needed")
      })
      .catch(() => setState("consent_needed"))
  }, [])

  useEffect(() => {
    if (state !== "ready") return
    startConversation()
      .then((convo) => setConversationId(convo.id))
      .catch(() => setError("Impossible de démarrer la conversation."))
  }, [state])

  const enableVoice = async () => {
    try {
      await grantConsent("VOICE")
      setState("ready")
    } catch {
      setError("Impossible d'activer les sessions vocales.")
    }
  }

  const speak = (text: string) => {
    if (muted || typeof window === "undefined" || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = "fr-FR"
    window.speechSynthesis.speak(utterance)
  }

  const send = async (text: string) => {
    if (!conversationId || !text.trim()) return
    const userTurn: VoiceTurn = { id: `u-${Date.now()}`, role: "user", content: text }
    const assistantId = `a-${Date.now()}`
    setTurns((prev) => [...prev, userTurn, { id: assistantId, role: "assistant", content: "" }])

    try {
      await streamMessage(conversationId, text, (event) => {
        if (event.type === "assistant_chunk") {
          setTurns((prev) => prev.map((t) => (t.id === assistantId ? { ...t, content: t.content + event.text } : t)))
        } else if (event.type === "assistant_correction") {
          setTurns((prev) => prev.map((t) => (t.id === assistantId ? { ...t, content: event.text } : t)))
        } else if (event.type === "assistant_message") {
          setTurns((prev) => prev.map((t) => (t.id === assistantId ? { ...t, content: event.content } : t)))
          speak(event.content)
        }
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        setState("anonymous")
      } else {
        setError("La réponse n'a pas pu être obtenue.")
      }
    }
  }

  const toggleListening = () => {
    const Recognition = getSpeechRecognition()
    if (!Recognition) return

    if (listening) {
      recognitionRef.current?.stop()
      return
    }

    const recognition = new Recognition()
    recognition.lang = "fr-FR"
    recognition.continuous = false
    recognition.interimResults = true
    recognition.onresult = (event) => {
      let finalText = ""
      let interimText = ""
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) finalText += result[0].transcript
        else interimText += result[0].transcript
      }
      setInterim(interimText)
      if (finalText.trim()) {
        setInterim("")
        send(finalText.trim())
      }
    }
    recognition.onend = () => {
      setListening(false)
      setInterim("")
    }
    recognition.onerror = () => {
      setListening(false)
      setInterim("")
      setError("La reconnaissance vocale a été interrompue.")
    }
    recognitionRef.current = recognition
    setError(null)
    setListening(true)
    recognition.start()
  }

  useEffect(() => () => recognitionRef.current?.stop(), [])

  if (state === "checking") {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Chargement…</div>
  }

  if (state === "anonymous") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour utiliser les sessions vocales.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  if (state === "unsupported") {
    return (
      <div className="mx-auto flex h-full w-full max-w-lg flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border bg-accent/40">
          <MicOff className="h-6 w-6 text-muted-foreground" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Reconnaissance vocale non disponible</h1>
        <p className="text-sm text-muted-foreground">
          Votre navigateur ne prend pas en charge la reconnaissance vocale nécessaire aux sessions parlées. Essayez
          avec une version récente de Chrome ou Edge.
        </p>
        <Button asChild className="mt-2">
          <Link href="/conversation">
            <MessageCircle className="h-4 w-4" strokeWidth={1.75} />
            Continuer par écrit
          </Link>
        </Button>
      </div>
    )
  }

  if (state === "consent_needed") {
    return (
      <div className="mx-auto flex h-full w-full max-w-lg flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border bg-accent/40">
          <Mic className="h-6 w-6 text-muted-foreground" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Activer les sessions vocales</h1>
        <p className="text-sm text-muted-foreground">
          Votre voix est transcrite localement par votre navigateur avant d&apos;être envoyée comme un message
          écrit — jamais enregistrée sur nos serveurs. Cette autorisation est révocable à tout moment dans les
          paramètres.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button className="mt-2" onClick={enableVoice}>
          Activer
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col px-6 py-8 md:py-10">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Session vocale</h1>
          <p className="text-sm text-muted-foreground">Parlez, l&apos;assistant vous répond à voix haute.</p>
        </div>
        <Button variant="ghost" size="icon" onClick={() => setMuted((m) => !m)} aria-label="Couper le son">
          {muted ? <VolumeX className="h-5 w-5" strokeWidth={1.75} /> : <Volume2 className="h-5 w-5" strokeWidth={1.75} />}
        </Button>
      </div>

      <div className="mt-6 flex-1 space-y-3 overflow-y-auto">
        {turns.length === 0 && (
          <Card>
            <CardContent className="p-5 text-sm text-muted-foreground">
              Appuyez sur le micro et parlez librement. Votre message apparaîtra ici une fois transcrit.
            </CardContent>
          </Card>
        )}
        {turns.map((t) => (
          <div key={t.id} className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                t.role === "user" ? "bg-primary text-primary-foreground" : "border bg-card"
              }`}
            >
              <p className="whitespace-pre-wrap">{t.content}</p>
            </div>
          </div>
        ))}
        {interim && (
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-xl bg-primary/40 px-4 py-2.5 text-sm italic text-primary-foreground">
              {interim}
            </div>
          </div>
        )}
      </div>

      {error && <p className="mt-3 text-center text-sm text-destructive">{error}</p>}

      <div className="mt-6 flex flex-col items-center gap-3">
        <Button
          size="lg"
          onClick={toggleListening}
          disabled={!conversationId}
          variant={listening ? "destructive" : "default"}
          className="h-16 w-16 rounded-full p-0"
          aria-label={listening ? "Arrêter l'écoute" : "Parler"}
        >
          {listening ? <MicOff className="h-6 w-6" strokeWidth={1.75} /> : <Mic className="h-6 w-6" strokeWidth={1.75} />}
        </Button>
        <Badge variant={listening ? "warning" : "outline"}>{listening ? "Écoute en cours…" : "Appuyez pour parler"}</Badge>
        <p className="text-center text-xs text-muted-foreground">
          Cet espace est confidentiel. En cas d&apos;urgence, contactez les secours (15, 112) ou le 3114.
        </p>
      </div>
    </div>
  )
}
