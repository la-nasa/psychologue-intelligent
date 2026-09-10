"use client"

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Mic, StopCircle, Pause, Play, Volume2, Waves, AlertCircle } from "lucide-react"

type VoiceState = 
  | "IDLE"
  | "LISTENING"
  | "PROCESSING"
  | "THINKING"
  | "SPEAKING"
  | "INTERRUPTED"
  | "ERROR"

interface Transcript {
  id: string
  text: string
  isFinal: boolean
  timestamp: Date
  speaker: "user" | "assistant"
}

export default function VoicePage() {
  const [voiceState, setVoiceState] = useState<VoiceState>("IDLE")
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const [isMuted, setIsMuted] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const [sessionDuration, setSessionDuration] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Simulate audio level when listening
  useEffect(() => {
    let interval: NodeJS.Timeout
    if (voiceState === "LISTENING" && !isMuted) {
      interval = setInterval(() => {
        setAudioLevel(Math.random() * 100)
      }, 100)
    } else {
      setAudioLevel(0)
    }
    return () => clearInterval(interval)
  }, [voiceState, isMuted])

  // Session timer
  useEffect(() => {
    let interval: NodeJS.Timeout
    if (voiceState !== "IDLE" && voiceState !== "ERROR") {
      interval = setInterval(() => {
        setSessionDuration((prev) => prev + 1)
      }, 1000)
    }
    return () => clearInterval(interval)
  }, [voiceState])

  const startListening = () => {
    setVoiceState("LISTENING")
    setTranscripts([])
    setSessionDuration(0)
    
    // Simulate transcription
    setTimeout(() => {
      const partialTranscript: Transcript = {
        id: "1",
        text: "Je me sens un peu...",
        isFinal: false,
        timestamp: new Date(),
        speaker: "user",
      }
      setTranscripts([partialTranscript])
      
      setTimeout(() => {
        const finalTranscript: Transcript = {
          ...partialTranscript,
          text: "Je me sens un peu anxieux cette semaine.",
          isFinal: true,
        }
        setTranscripts([finalTranscript])
        setVoiceState("PROCESSING")
        
        setTimeout(() => {
          setVoiceState("THINKING")
          
          setTimeout(() => {
            const aiResponse: Transcript = {
              id: "2",
              text: "Je comprends. Pouvez-vous me dire ce qui vous rend anxieux ?",
              isFinal: true,
              timestamp: new Date(),
              speaker: "assistant",
            }
            setTranscripts((prev) => [...prev, aiResponse])
            setVoiceState("SPEAKING")
            
            setTimeout(() => {
              setVoiceState("LISTENING")
            }, 3000)
          }, 1500)
        }, 1000)
      }, 1500)
    }, 500)
  }

  const stopListening = () => {
    setVoiceState("IDLE")
  }

  const toggleMute = () => {
    setIsMuted(!isMuted)
  }

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`
  }

  const getStateColor = () => {
    switch (voiceState) {
      case "LISTENING":
        return "text-green-600"
      case "PROCESSING":
      case "THINKING":
        return "text-yellow-600"
      case "SPEAKING":
        return "text-blue-600"
      case "ERROR":
        return "text-red-600"
      default:
        return "text-muted-foreground"
    }
  }

  const getStateLabel = () => {
    const labels: Record<VoiceState, string> = {
      IDLE: "Prêt",
      LISTENING: "Écoute en cours...",
      PROCESSING: "Traitement...",
      THINKING: "Réflexion...",
      SPEAKING: "Parole...",
      INTERRUPTED: "Interrompu",
      ERROR: "Erreur",
    }
    return labels[voiceState]
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Session Vocale</h2>
            <p className="text-sm text-muted-foreground">
              {formatDuration(sessionDuration)} • {getStateLabel()}
            </p>
          </div>
          <Badge variant={voiceState === "LISTENING" ? "default" : "secondary"}>
            {voiceState === "LISTENING" ? "En direct" : "Pause"}
          </Badge>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {/* Voice Visualizer */}
          <Card>
            <CardHeader className="text-center">
              <CardTitle className="flex items-center justify-center gap-2">
                <Waves className={`h-6 w-6 ${getStateColor()}`} />
                Assistant Vocal
              </CardTitle>
              <CardDescription>
                Parlez naturellement, l'IA vous écoute et répond
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Audio Level Indicator */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Niveau audio</span>
                  <span>{Math.round(audioLevel)}%</span>
                </div>
                <Progress value={audioLevel} className="h-3" />
              </div>

              {/* State Indicator */}
              <div className="flex items-center justify-center py-4">
                <div
                  className={`flex h-32 w-32 items-center justify-center rounded-full border-4 transition-all duration-300 ${
                    voiceState === "LISTENING"
                      ? "border-green-500 bg-green-50 animate-pulse"
                      : voiceState === "SPEAKING"
                      ? "border-blue-500 bg-blue-50"
                      : voiceState === "PROCESSING" || voiceState === "THINKING"
                      ? "border-yellow-500 bg-yellow-50"
                      : "border-gray-200 bg-gray-50"
                  }`}
                >
                  {voiceState === "LISTENING" && <Mic className={`h-12 w-12 ${getStateColor()}`} />}
                  {voiceState === "SPEAKING" && <Volume2 className={`h-12 w-12 ${getStateColor()}`} />}
                  {(voiceState === "PROCESSING" || voiceState === "THINKING") && (
                    <AlertCircle className={`h-12 w-12 ${getStateColor()}`} />
                  )}
                  {voiceState === "IDLE" && <Mic className="h-12 w-12 text-muted-foreground" />}
                </div>
              </div>

              {/* Controls */}
              <div className="flex justify-center gap-4">
                {voiceState === "IDLE" || voiceState === "ERROR" ? (
                  <Button onClick={startListening} size="lg" className="w-32">
                    <Mic className="mr-2 h-5 w-5" />
                    Démarrer
                  </Button>
                ) : (
                  <>
                    <Button
                      variant="outline"
                      size="lg"
                      onClick={toggleMute}
                      className={isMuted ? "text-red-600" : ""}
                    >
                      {isMuted ? (
                        <AlertCircle className="h-5 w-5" />
                      ) : (
                        <Pause className="h-5 w-5" />
                      )}
                    </Button>
                    <Button onClick={stopListening} size="lg" variant="destructive" className="w-32">
                      <StopCircle className="mr-2 h-5 w-5" />
                      Arrêter
                    </Button>
                  </>
                )}
              </div>

              {/* Tips */}
              <div className="rounded-lg bg-muted p-4 text-sm">
                <p className="font-medium mb-2">Conseils :</p>
                <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                  <li>Parlez naturellement comme à un psychologue</li>
                  <li>Vous pouvez interrompre l'IA à tout moment</li>
                  <li>Les pauses sont normales et attendues</li>
                  <li>Cliquez sur "Arrêter" pour terminer la session</li>
                </ul>
              </div>
            </CardContent>
          </Card>

          {/* Live Transcript */}
          {transcripts.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Transcription en direct</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-48" ref={scrollRef}>
                  <div className="space-y-3">
                    {transcripts.map((transcript) => (
                      <div
                        key={transcript.id}
                        className={`rounded-lg p-3 ${
                          transcript.speaker === "user"
                            ? "bg-primary/10"
                            : "bg-muted"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm flex-1">
                            {transcript.text}
                            {!transcript.isFinal && (
                              <span className="animate-pulse">▊</span>
                            )}
                          </p>
                          <span className="text-xs text-muted-foreground whitespace-nowrap">
                            {transcript.timestamp.toLocaleTimeString("fr-FR", {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
