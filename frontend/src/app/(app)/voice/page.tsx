"use client"

import { useCallback, useEffect, useRef, useState } from "react"
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
import { EMERGENCY_BANNER } from "@/lib/emergency"

interface VoiceTurn {
  id: string
  role: "user" | "assistant"
  content: string
}

type SetupState = "checking" | "anonymous" | "unsupported" | "consent_needed" | "ready"
type VoiceUiState =
  | "IDLE"
  | "LISTENING"
  | "PROCESSING"
  | "THINKING"
  | "SPEAKING"
  | "INTERRUPTED"
  | "RECONNECTING"
  | "ERROR"

const STATE_LABEL: Record<VoiceUiState, string> = {
  IDLE: "Appuyez pour parler",
  LISTENING: "Écoute…",
  PROCESSING: "Transcription…",
  THINKING: "Réflexion…",
  SPEAKING: "L’assistant parle — appuyez pour interrompre",
  INTERRUPTED: "Interrompu",
  RECONNECTING: "Reconnexion…",
  ERROR: "Erreur — réessayez",
}

interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: { transcript: string }
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>
  resultIndex: number
}
interface SpeechRecognitionErrorEventLike {
  error?: string
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  abort(): void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onend: (() => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
}

function getSpeechRecognition(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as Record<string, unknown>
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => SpeechRecognitionLike) | null
}

function stopBrowserSpeech() {
  if (typeof window === "undefined" || !window.speechSynthesis) return
  window.speechSynthesis.cancel()
}

export default function VoicePage() {
  const [setup, setSetup] = useState<SetupState>("checking")
  const [ui, setUi] = useState<VoiceUiState>("IDLE")
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [turns, setTurns] = useState<VoiceTurn[]>([])
  const [interim, setInterim] = useState("")
  const [muted, setMuted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const speakingRef = useRef(false)
  const turnAbortRef = useRef(false)

  const ensureConversation = useCallback(async (): Promise<string | null> => {
    if (conversationId) return conversationId
    try {
      setUi("RECONNECTING")
      const convo = await startConversation()
      setConversationId(convo.id)
      setUi("IDLE")
      return convo.id
    } catch {
      setError("Impossible de démarrer ou de reprendre la conversation. Vérifiez le réseau puis réessayez.")
      setUi("ERROR")
      return null
    }
  }, [conversationId])

  useEffect(() => {
    if (!getToken()) {
      setSetup("anonymous")
      return
    }
    if (!getSpeechRecognition()) {
      setSetup("unsupported")
      return
    }
    listConsents()
      .then((consents) => {
        const active = consents.find((c) => c.purpose === "VOICE")?.active ?? false
        setSetup(active ? "ready" : "consent_needed")
      })
      .catch(() => setSetup("consent_needed"))
  }, [])

  useEffect(() => {
    if (setup !== "ready") return
    void ensureConversation()
  }, [setup, ensureConversation])

  const enableVoice = async () => {
    try {
      await grantConsent("VOICE")
      setSetup("ready")
    } catch {
      setError("Impossible d'activer les sessions vocales.")
    }
  }

  const speak = (text: string) => {
    if (muted || typeof window === "undefined" || !window.speechSynthesis) {
      setUi("IDLE")
      return
    }
    stopBrowserSpeech()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = "fr-FR"
    speakingRef.current = true
    setUi("SPEAKING")
    utterance.onend = () => {
      speakingRef.current = false
      setUi("IDLE")
    }
    utterance.onerror = () => {
      speakingRef.current = false
      setUi("IDLE")
    }
    window.speechSynthesis.speak(utterance)
  }

  const bargeIn = () => {
    turnAbortRef.current = true
    stopBrowserSpeech()
    speakingRef.current = false
    recognitionRef.current?.abort()
    setUi("INTERRUPTED")
    setInterim("")
  }

  const send = async (text: string, cid: string, retry = true) => {
    const userTurn: VoiceTurn = { id: `u-${Date.now()}`, role: "user", content: text }
    const assistantId = `a-${Date.now()}`
    turnAbortRef.current = false
    setTurns((prev) => [...prev, userTurn, { id: assistantId, role: "assistant", content: "" }])
    setUi("THINKING")

    try {
      await streamMessage(cid, text, (event) => {
        if (turnAbortRef.current) return
        if (event.type === "assistant_chunk") {
          setUi("THINKING")
          setTurns((prev) => prev.map((t) => (t.id === assistantId ? { ...t, content: t.content + event.text } : t)))
        } else if (event.type === "assistant_correction") {
          setTurns((prev) => prev.map((t) => (t.id === assistantId ? { ...t, content: event.text } : t)))
        } else if (event.type === "assistant_message") {
          setTurns((prev) => prev.map((t) => (t.id === assistantId ? { ...t, content: event.content } : t)))
          if (!turnAbortRef.current) speak(event.content)
        }
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        setSetup("anonymous")
        return
      }
      if (retry) {
        setUi("RECONNECTING")
        const fresh = await ensureConversation()
        if (fresh) {
          await send(text, fresh, false)
          return
        }
      }
      setError("La réponse n'a pas pu être obtenue. Vous pouvez réessayer ou continuer par écrit.")
      setUi("ERROR")
    }
  }

  const startListening = () => {
    const Recognition = getSpeechRecognition()
    if (!Recognition) return

    if (speakingRef.current || ui === "SPEAKING") {
      bargeIn()
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
        setUi("PROCESSING")
        const cid = conversationId
        if (cid) void send(finalText.trim(), cid)
        else {
          void ensureConversation().then((id) => {
            if (id) void send(finalText.trim(), id)
          })
        }
      }
    }
    recognition.onend = () => {
      recognitionRef.current = null
      setInterim("")
      setUi((current) => (current === "LISTENING" ? "IDLE" : current))
    }
    recognition.onerror = (event) => {
      recognitionRef.current = null
      setInterim("")
      if (event.error === "not-allowed") {
        setError("Le microphone est refusé. Autorisez-le dans le navigateur, ou continuez par écrit.")
        setUi("ERROR")
        return
      }
      if (event.error === "aborted") {
        setUi("INTERRUPTED")
        return
      }
      setError("La reconnaissance vocale a été interrompue. Réessayez dans un endroit plus calme.")
      setUi("ERROR")
    }
    recognitionRef.current = recognition
    setError(null)
    setUi("LISTENING")
    try {
      recognition.start()
    } catch {
      setError("Impossible de démarrer le microphone.")
      setUi("ERROR")
    }
  }

  const toggleListening = () => {
    if (ui === "LISTENING") {
      recognitionRef.current?.stop()
      setUi("IDLE")
      return
    }
    if (ui === "SPEAKING" || speakingRef.current) {
      bargeIn()
      startListening()
      return
    }
    void (async () => {
      const cid = await ensureConversation()
      if (!cid) return
      startListening()
    })()
  }

  useEffect(
    () => () => {
      recognitionRef.current?.abort()
      stopBrowserSpeech()
    },
    [],
  )

  if (setup === "checking") {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Chargement…</div>
  }

  if (setup === "anonymous") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">Connectez-vous pour utiliser les sessions vocales.</p>
        <Button asChild>
          <Link href="/login">Se connecter</Link>
        </Button>
      </div>
    )
  }

  if (setup === "unsupported") {
    return (
      <div className="mx-auto flex h-full w-full max-w-lg flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border bg-accent/40">
          <MicOff className="h-6 w-6 text-muted-foreground" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Reconnaissance vocale non disponible</h1>
        <p className="text-sm text-muted-foreground">
          Votre navigateur ne prend pas en charge la reconnaissance vocale nécessaire aux sessions parlées. Essayez
          avec une version récente de Chrome ou Edge, ou continuez par écrit.
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

  if (setup === "consent_needed") {
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

  const micBusy = ui === "LISTENING"
  const canTalk = Boolean(conversationId) || ui === "RECONNECTING"

  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col px-6 py-8 md:py-10">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Session vocale</h1>
          <p className="text-sm text-muted-foreground">Parlez, l&apos;assistant vous répond à voix haute.</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => {
            setMuted((m) => {
              if (!m) stopBrowserSpeech()
              return !m
            })
          }}
          aria-label="Couper le son"
        >
          {muted ? <VolumeX className="h-5 w-5" strokeWidth={1.75} /> : <Volume2 className="h-5 w-5" strokeWidth={1.75} />}
        </Button>
      </div>

      <div className="mt-6 flex-1 space-y-3 overflow-y-auto" aria-live="polite">
        {turns.length === 0 && (
          <Card>
            <CardContent className="p-5 text-sm text-muted-foreground">
              Appuyez sur le micro et parlez librement. Votre message apparaîtra ici une fois transcrit. Vous pouvez
              interrompre la voix à tout moment.
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

      {error && (
        <p className="mt-3 text-center text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="mt-6 flex flex-col items-center gap-3">
        <Button
          size="lg"
          onClick={toggleListening}
          disabled={!canTalk && ui !== "ERROR"}
          variant={micBusy ? "destructive" : "default"}
          className="h-16 w-16 rounded-full p-0"
          aria-label={micBusy ? "Arrêter l'écoute" : ui === "SPEAKING" ? "Interrompre et parler" : "Parler"}
        >
          {micBusy ? <MicOff className="h-6 w-6" strokeWidth={1.75} /> : <Mic className="h-6 w-6" strokeWidth={1.75} />}
        </Button>
        <Badge variant={micBusy || ui === "SPEAKING" ? "warning" : "outline"}>{STATE_LABEL[ui]}</Badge>
        <p className="text-center text-xs text-muted-foreground">
          {EMERGENCY_BANNER}
        </p>
      </div>
    </div>
  )
}
