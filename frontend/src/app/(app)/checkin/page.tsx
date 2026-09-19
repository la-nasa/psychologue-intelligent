"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader } from "@/components/layout/PageShell"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { CheckCircle2, ArrowRight } from "lucide-react"
import { ApiError, Phq9SubmitResult, submitPhq9 } from "@/lib/api"
import { EMERGENCY_IMMEDIATE } from "@/lib/emergency"

const QUESTIONS = [
  "Peu d'intérêt ou de plaisir à faire les choses",
  "Se sentir triste, déprimé(e), ou désespéré(e)",
  "Difficultés à s'endormir, à rester endormi(e), ou dormir trop",
  "Se sentir fatigué(e) ou avoir peu d'énergie",
  "Peu d'appétit ou manger trop",
  "Mauvaise opinion de vous-même — ou sentiment d'être un échec, d'avoir déçu votre entourage",
  "Difficultés à vous concentrer, par exemple pour lire ou regarder un programme",
  "Bouger ou parler si lentement que cela aurait pu être remarqué — ou au contraire être si agité(e) que vous avez bougé bien plus que d'habitude",
  "Penser qu'il vaudrait mieux être mort(e), ou penser à vous faire du mal",
]

const OPTIONS = [
  { value: 0, label: "Jamais" },
  { value: 1, label: "Plusieurs jours" },
  { value: 2, label: "Plus de la moitié des jours" },
  { value: 3, label: "Presque tous les jours" },
]

export default function CheckinPage() {
  const [answers, setAnswers] = useState<(number | null)[]>(Array(9).fill(null))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Phq9SubmitResult | null>(null)

  const complete = answers.every((a) => a !== null)

  const submit = async () => {
    if (!complete) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await submitPhq9(answers as number[])
      setResult(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'enregistrer ce questionnaire.")
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    const needsSupport = result.item9_score > 0
    return (
      <div className="mx-auto w-full max-w-2xl space-y-6 px-5 py-10 pb-24 md:px-8 md:pb-10">
        <Card className="border-primary/15">
          <CardContent className="space-y-4 p-6 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-success" strokeWidth={1.5} />
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Check-in enregistré</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Score : <span className="tabular-nums font-medium text-foreground">{result.total_score}/27</span> — {result.severity_band}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Indicateur d&apos;auto-questionnaire, pas un diagnostic. Seul un professionnel peut interpréter ce résultat avec vous.
              </p>
            </div>
            {result.alert_created && (
              <Badge variant="warning">Votre clinicien a été notifié</Badge>
            )}
          </CardContent>
        </Card>

        {needsSupport && (
          <Card className="border-destructive/30 bg-destructive/5">
            <CardContent className="space-y-2 p-5 text-sm">
              <p className="font-medium">Vous avez indiqué avoir pensé à vous faire du mal.</p>
              <p className="text-muted-foreground">
                {EMERGENCY_IMMEDIATE}
              </p>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap gap-3">
          <Button asChild>
            <Link href="/conversation">Parler à l&apos;assistant <ArrowRight className="h-4 w-4" strokeWidth={1.75} /></Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/">Retour à l&apos;accueil</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 px-5 py-8 pb-24 md:px-8 md:py-10 md:pb-10">
      <PageHeader
        title="Check-in rapide"
        description="Sur les deux dernières semaines, à quelle fréquence avez-vous été gêné(e) par les problèmes suivants ? Questionnaire PHQ-9 utilisé ici comme check-in de suivi, pas comme diagnostic."
      />

      <div className="space-y-5">
        {QUESTIONS.map((question, idx) => (
          <div key={idx} className="space-y-2.5 border-b pb-5 last:border-0">
            <p className="text-sm font-medium leading-relaxed text-balance">{idx + 1}. {question}</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setAnswers((prev) => prev.map((a, i) => (i === idx ? opt.value : a)))}
                  className={cn(
                    "min-h-11 rounded-xl border px-3 py-2 text-xs font-medium tracking-tight transition-colors",
                    answers[idx] === opt.value
                      ? "border-primary bg-primary text-primary-foreground"
                      : "hover:border-primary/40 hover:bg-accent",
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button onClick={submit} disabled={!complete || submitting} size="lg">
        {submitting ? "Envoi…" : "Envoyer mon check-in"}
      </Button>
    </div>
  )
}
