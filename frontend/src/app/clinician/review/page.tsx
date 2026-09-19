"use client"

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Check, MessageSquareWarning } from "lucide-react"
import {
  AI_REVIEW_SCORE_DIMENSIONS,
  AiReviewDecision,
  AiReviewFeedbackCategory,
  ApiError,
  ClinicianPatientItem,
  ReviewableMessage,
  listClinicianPatients,
  listReviewableMessages,
  submitAiReview,
} from "@/lib/api"

const DECISIONS: { value: AiReviewDecision; label: string }[] = [
  { value: "APPROVE", label: "Approuver" },
  { value: "EDIT", label: "Corriger" },
  { value: "REJECT", label: "Rejeter" },
  { value: "FLAG_SAFETY", label: "Signaler un risque de sûreté" },
]

const CATEGORIES: { value: AiReviewFeedbackCategory; label: string }[] = [
  { value: "TONE", label: "Ton" },
  { value: "CLINICAL_ACCURACY", label: "Justesse clinique" },
  { value: "PERSONALIZATION", label: "Personnalisation" },
  { value: "CONTEXT_UNDERSTANDING", label: "Compréhension du contexte" },
  { value: "SAFETY", label: "Sûreté" },
  { value: "RELEVANCE", label: "Pertinence" },
  { value: "OTHER", label: "Autre" },
]

const DIMENSION_LABELS: Record<string, string> = {
  empathy: "Empathie",
  relevance: "Pertinence",
  personalization: "Personnalisation",
  context: "Contexte",
  safety: "Sûreté",
  clarity: "Clarté",
  usefulness: "Utilité",
}

function ReviewForm({ message, onSubmitted }: { message: ReviewableMessage; onSubmitted: () => void }) {
  const [decision, setDecision] = useState<AiReviewDecision>("APPROVE")
  const [category, setCategory] = useState<AiReviewFeedbackCategory>("RELEVANCE")
  const [scores, setScores] = useState<Record<string, number>>(
    Object.fromEntries(AI_REVIEW_SCORE_DIMENSIONS.map((d) => [d, 3])),
  )
  const [correction, setCorrection] = useState("")
  const [comment, setComment] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async () => {
    setError(null)
    if (decision === "EDIT" && !correction.trim()) {
      setError("Une correction est requise pour la décision « Corriger ».")
      return
    }
    setSubmitting(true)
    try {
      await submitAiReview(message.message_id, {
        decision,
        scores,
        feedback_category: category,
        corrected_response: correction,
        clinical_comment: comment,
      })
      setDone(true)
      onSubmitted()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'enregistrer cette revue.")
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <p className="flex items-center gap-2 rounded-md bg-success/10 px-3 py-2 text-sm text-success">
        <Check className="h-4 w-4" strokeWidth={1.75} /> Revue enregistrée.
      </p>
    )
  }

  return (
    <div className="space-y-3 border-t pt-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Décision</label>
          <Select value={decision} onValueChange={(v) => setDecision(v as AiReviewDecision)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {DECISIONS.map((d) => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Catégorie de retour</label>
          <Select value={category} onValueChange={(v) => setCategory(v as AiReviewFeedbackCategory)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {AI_REVIEW_SCORE_DIMENSIONS.map((dim) => (
          <div key={dim} className="space-y-1">
            <label className="text-xs text-muted-foreground">{DIMENSION_LABELS[dim]}</label>
            <Select value={String(scores[dim])} onValueChange={(v) => setScores((s) => ({ ...s, [dim]: Number(v) }))}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[1, 2, 3, 4, 5].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        ))}
      </div>

      {decision === "EDIT" && (
        <Textarea
          placeholder="Réponse corrigée (obligatoire)"
          value={correction}
          onChange={(e) => setCorrection(e.target.value)}
          className="min-h-20 text-sm"
        />
      )}
      <Textarea
        placeholder="Commentaire clinique (optionnel)"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        className="min-h-16 text-sm"
      />

      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button size="sm" onClick={submit} disabled={submitting}>
        {submitting ? "Envoi…" : "Enregistrer la revue"}
      </Button>
    </div>
  )
}

export default function AiReviewPage() {
  const [patients, setPatients] = useState<ClinicianPatientItem[]>([])
  const [patientId, setPatientId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ReviewableMessage[] | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listClinicianPatients()
      .then((items) => {
        setPatients(items)
        if (items.length > 0) setPatientId(items[0].patient_id)
      })
      .catch(() => setError("Impossible de charger vos patients."))
  }, [])

  const loadMessages = useCallback(() => {
    if (!patientId) return
    listReviewableMessages(patientId)
      .then(setMessages)
      .catch(() => setError("Impossible de charger les réponses de l'assistant."))
  }, [patientId])

  useEffect(() => {
    loadMessages()
  }, [loadMessages])

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-5 py-8 md:px-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Revue des réponses IA</h1>
        <p className="text-sm text-muted-foreground">
          Usage non punitif : les revues mesurent la qualité du modèle, jamais celle du relecteur.
        </p>
      </div>

      {patients.length === 0 ? (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">Aucun patient suivi pour l&apos;instant.</CardContent></Card>
      ) : (
        <Select value={patientId ?? undefined} onValueChange={setPatientId}>
          <SelectTrigger className="w-72"><SelectValue placeholder="Choisir un patient" /></SelectTrigger>
          <SelectContent>
            {patients.map((p) => (
              <SelectItem key={p.patient_id} value={p.patient_id}>{p.display_name || p.patient_id.slice(0, 8)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="space-y-3">
        {messages?.length === 0 && (
          <p className="text-sm text-muted-foreground">Aucune réponse de l&apos;assistant pour ce patient.</p>
        )}
        {messages?.map((m) => (
          <Card key={m.message_id}>
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline">{m.generation_path}</Badge>
                  {m.model_version && <span>{m.model_version}</span>}
                  <span>{new Date(m.created_at).toLocaleString("fr-FR")}</span>
                </div>
                {m.reviewed_by_me ? (
                  <Badge variant="success">Déjà revue par vous</Badge>
                ) : m.reviewed ? (
                  <Badge variant="outline">Revue par un autre clinicien</Badge>
                ) : (
                  <Badge variant="warning" className="flex items-center gap-1">
                    <MessageSquareWarning className="h-3 w-3" strokeWidth={1.75} /> À revoir
                  </Badge>
                )}
              </div>
              {m.patient_message && (
                <p className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Patient : </span>{m.patient_message}
                </p>
              )}
              <p className="rounded-md border p-3 text-sm">
                <span className="font-medium">Assistant : </span>{m.assistant_response}
              </p>

              {m.reviewed_by_me ? null : expanded === m.message_id ? (
                <ReviewForm message={m} onSubmitted={loadMessages} />
              ) : (
                <Button size="sm" variant="outline" onClick={() => setExpanded(m.message_id)}>
                  Revoir cette réponse
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
