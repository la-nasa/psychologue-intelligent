const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

const TOKEN_KEY = "pi_access_token"

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // localStorage indisponible (navigation privée, quota) : la session ne survit pas au rechargement.
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    // rien à faire
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json()
    return body?.detail ?? body?.error?.message ?? fallback
  } catch {
    return fallback
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers = new Headers(init?.headers)
  headers.set("Content-Type", "application/json")
  if (token) headers.set("Authorization", `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorMessage(res, res.statusText))
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export async function register(organizationSlug: string, email: string, password: string): Promise<void> {
  await request<void>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ organization_slug: organizationSlug, email, password }),
  })
}

export async function login(
  organizationSlug: string,
  email: string,
  password: string,
  totpCode?: string,
): Promise<TokenResponse> {
  const body: Record<string, string> = { organization_slug: organizationSlug, email, password }
  if (totpCode) body.totp_code = totpCode
  const res = await request<TokenResponse>("/api/v1/auth/sessions", {
    method: "POST",
    body: JSON.stringify(body),
  })
  setToken(res.access_token)
  return res
}

export async function logout(): Promise<void> {
  try {
    await request<void>("/api/v1/auth/logout", { method: "POST" })
  } finally {
    clearToken()
  }
}

export interface MeResponse {
  id: string
  email: string
  organization_id: string
  roles: string[]
}

export async function getMe(): Promise<MeResponse> {
  return request<MeResponse>("/api/v1/me")
}

/** Route d'atterrissage après connexion, selon le rôle le plus « élevé » du compte. */
export function landingPathForRoles(roles: string[]): string {
  if (roles.includes("PSYCHOLOGIST") || roles.includes("CLINICAL_SUPERVISOR")) return "/clinician"
  if (roles.includes("ADMIN") || roles.includes("SUPER_ADMIN")) return "/admin"
  return "/conversation"
}

// --- MFA (server/app/api/auth.py) ---

export interface MfaEnrollment {
  secret: string
  otpauth_uri: string
}

export async function enrollMfa(): Promise<MfaEnrollment> {
  return request<MfaEnrollment>("/api/v1/auth/mfa/enroll", { method: "POST" })
}

export async function activateMfa(code: string): Promise<void> {
  await request<void>("/api/v1/auth/mfa/activate", { method: "POST", body: JSON.stringify({ code }) })
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await request<void>("/api/v1/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export interface SessionItem {
  id: string
  created_at: string
  expires_at: string
  current: boolean
}

export async function listSessions(): Promise<SessionItem[]> {
  const res = await request<{ items: SessionItem[] }>("/api/v1/auth/sessions")
  return res.items
}

export async function revokeSession(sessionId: string): Promise<void> {
  await request<void>(`/api/v1/auth/sessions/${sessionId}`, { method: "DELETE" })
}

// --- Rappels de check-in PHQ-9 (server/app/api/assessment.py) ---

export interface ReminderItem {
  id: string
  instrument: string
  due_at: string
  status: "PENDING" | "SENT" | "DONE" | "CANCELLED"
}

export async function scheduleReminder(dueAt: string): Promise<{ id: string }> {
  return request<{ id: string }>("/api/v1/assessments/reminders", {
    method: "POST",
    body: JSON.stringify({ due_at: dueAt }),
  })
}

export async function listReminders(): Promise<ReminderItem[]> {
  const res = await request<{ items: ReminderItem[] }>("/api/v1/assessments/reminders")
  return res.items
}

export interface ConversationResponse {
  id: string
  status: string
}

export async function startConversation(): Promise<ConversationResponse> {
  return request<ConversationResponse>("/api/v1/conversations", { method: "POST" })
}

export interface MessageItem {
  id: string
  author_type: string
  content: string
  sequence_no: number
  created_at: string
}

export async function listMessages(conversationId: string): Promise<MessageItem[]> {
  const res = await request<{ items: MessageItem[] }>(`/api/v1/conversations/${conversationId}/messages`)
  return res.items
}

// --- Objectifs (server/app/api/goals.py) ---

export interface GoalItem {
  id: string
  title: string
  description: string
  status: string
  progress: number
}

export async function listGoals(): Promise<GoalItem[]> {
  const res = await request<{ items: GoalItem[] }>("/api/v1/goals")
  return res.items
}

export async function createGoal(title: string, description: string): Promise<{ id: string }> {
  return request<{ id: string }>("/api/v1/goals", { method: "POST", body: JSON.stringify({ title, description }) })
}

export async function recordGoalProgress(goalId: string, value: number, note = ""): Promise<void> {
  await request<void>(`/api/v1/goals/${goalId}/progress`, { method: "POST", body: JSON.stringify({ value, note }) })
}

// --- Profil (server/app/api/account.py) ---

export interface ProfileData {
  display_name: string
  about_me: string
  language: "fr" | "en"
  onboarding_completed_at: string | null
}

export async function getProfile(): Promise<ProfileData> {
  return request<ProfileData>("/api/v1/profile")
}

export async function saveProfile(displayName: string, aboutMe: string, language: "fr" | "en"): Promise<void> {
  await request<void>("/api/v1/profile", {
    method: "POST",
    body: JSON.stringify({ display_name: displayName, about_me: aboutMe, language }),
  })
}

export interface Preferences {
  tone: "warm" | "neutral" | "direct"
  response_length: "short" | "medium" | "detailed"
  question_frequency: "low" | "medium" | "high"
  directiveness: "reflective" | "balanced" | "directive"
}

export async function getPreferences(): Promise<Preferences> {
  return request<Preferences>("/api/v1/profile/preferences")
}

export async function savePreferences(prefs: Preferences): Promise<void> {
  await request<void>("/api/v1/profile/preferences", { method: "PUT", body: JSON.stringify(prefs) })
}

export async function requestAccountDeletion(): Promise<void> {
  await request<void>("/api/v1/privacy/deletion-requests", { method: "POST" })
}

// --- Consentement (server/app/api/account.py) ---

export type ConsentPurpose = "CARE" | "LEARNING" | "AI_EXTERNAL" | "VOICE" | "ANALYTICS" | "RESEARCH"

export interface ConsentItem {
  purpose: ConsentPurpose
  version: string
  granted_at: string
  revoked_at: string | null
  active: boolean
}

export async function listConsents(): Promise<ConsentItem[]> {
  const res = await request<{ items: ConsentItem[] }>("/api/v1/consents")
  return res.items
}

export async function grantConsent(purpose: ConsentPurpose): Promise<void> {
  await request<void>("/api/v1/consents", { method: "POST", body: JSON.stringify({ purpose }) })
}

export async function revokeConsent(purpose: ConsentPurpose): Promise<void> {
  await request<void>("/api/v1/consents/revoke", { method: "POST", body: JSON.stringify({ purpose }) })
}

// --- PHQ-9 (server/app/api/assessment.py) ---

export interface Phq9SubmitResult {
  id: string
  instrument_version: string
  total_score: number
  item9_score: number
  severity_band: string
  alert_level: string | null
  alert_created: boolean
}

export async function submitPhq9(answers: number[]): Promise<Phq9SubmitResult> {
  return request<Phq9SubmitResult>("/api/v1/assessments/phq9", { method: "POST", body: JSON.stringify({ answers }) })
}

export interface Phq9HistoryItem {
  id: string
  total_score: number
  item9_score: number
  severity_band: string
  completed_at: string
}

export async function getPhq9History(): Promise<Phq9HistoryItem[]> {
  const res = await request<{ items: Phq9HistoryItem[] }>("/api/v1/assessments/phq9")
  return res.items
}

export interface Phq9Trend {
  latest: Phq9HistoryItem | null
  previous: Phq9HistoryItem | null
  delta: number | null
  direction: "improving" | "worsening" | "stable" | "first" | "no_data"
}

export async function getPhq9Trend(): Promise<Phq9Trend> {
  return request<Phq9Trend>("/api/v1/assessments/phq9/trend")
}

// --- Alertes cliniciennes (server/app/api/clinician.py — PSYCHOLOGIST/CLINICAL_SUPERVISOR uniquement) ---

export interface ClinicianAlertItem {
  id: string
  patient_id: string
  level: "GREEN" | "ORANGE" | "RED" | "UNKNOWN"
  status: string
  source: string
  score: number | null
  policy_version: string | null
  sla_due_at: string | null
  assigned_clinician_id: string | null
  created_at: string
  acknowledged_at: string | null
}

export async function listClinicianAlerts(level?: string, status?: string): Promise<ClinicianAlertItem[]> {
  const params = new URLSearchParams()
  if (level) params.set("level", level)
  if (status) params.set("status", status)
  const qs = params.toString()
  const res = await request<{ items: ClinicianAlertItem[] }>(`/api/v1/clinician/alerts${qs ? `?${qs}` : ""}`)
  return res.items
}

export type AlertActionTarget = "ACKNOWLEDGED" | "IN_REVIEW" | "ESCALATED" | "RESOLVED" | "CANCELLED"

export async function actOnAlert(
  alertId: string,
  target: AlertActionTarget,
  justification = "",
): Promise<ClinicianAlertItem> {
  return request<ClinicianAlertItem>(`/api/v1/clinician/alerts/${alertId}/actions`, {
    method: "POST",
    body: JSON.stringify({ target, justification }),
  })
}

// --- Plateforme clinicien (server/app/api/clinician.py) ---

export interface ClinicianOverview {
  patients_followed: number
  open_alerts: { total: number; red: number; orange: number }
  sla_breached: number
  assigned_to_me: number
  generated_at: string
}

export async function getClinicianOverview(): Promise<ClinicianOverview> {
  return request<ClinicianOverview>("/api/v1/clinician/overview")
}

export interface ClinicianPatientItem {
  patient_id: string
  display_name: string
  latest_phq9: {
    total_score: number
    item9_score: number
    severity_band: string
    completed_at: string
  } | null
  open_alert_count: number
}

export async function listClinicianPatients(): Promise<ClinicianPatientItem[]> {
  const res = await request<{ items: ClinicianPatientItem[] }>("/api/v1/clinician/patients")
  return res.items
}

export interface AlertActionEntry {
  id: string
  alert_id: string
  actor_id: string | null
  action: string
  justification: string
  created_at: string
}

export interface PatientTimeline {
  patient_id: string
  display_name: string
  phq9_history: Phq9HistoryItem[]
  phq9_trend: Phq9Trend
  alerts: ClinicianAlertItem[]
  alert_actions: AlertActionEntry[]
}

export async function getPatientTimeline(patientId: string): Promise<PatientTimeline> {
  return request<PatientTimeline>(`/api/v1/clinician/patients/${patientId}/timeline`)
}

export interface EvidenceRef {
  type: string
  id: string
}

export interface SummaryStatement {
  key: string
  category: "assessment" | "safety" | "risk" | "engagement" | "goals" | "consent"
  text: string
  evidence: EvidenceRef[]
  as_of: string | null
}

export interface PatientSummary {
  patient_id: string
  generated_at: string
  disclaimer: string
  statements: SummaryStatement[]
}

export async function getPatientSummary(patientId: string): Promise<PatientSummary> {
  return request<PatientSummary>(`/api/v1/clinician/patients/${patientId}/summary`)
}

export interface Patient360 {
  patient_id: string
  display_name: string
  consents: ConsentItem[]
  summary: PatientSummary
  goals: { id: string; title: string; status: string; created_at: string }[]
  phq9_history: Phq9HistoryItem[]
  phq9_trend: Phq9Trend
  alerts: ClinicianAlertItem[]
  alert_actions: AlertActionEntry[]
}

export async function getPatient360(patientId: string): Promise<Patient360> {
  return request<Patient360>(`/api/v1/clinician/patients/${patientId}/360`)
}

// --- Revue IA clinicienne (server/app/api/ai_review.py) ---

export interface ReviewableMessage {
  message_id: string
  conversation_id: string
  assistant_response: string
  patient_message: string | null
  generation_path: string
  model_version: string | null
  created_at: string
  reviewed: boolean
  reviewed_by_me: boolean
}

/** Les 7 dimensions notées 1..5 (server/app/application/ai_review.py SCORE_DIMENSIONS). */
export const AI_REVIEW_SCORE_DIMENSIONS = [
  "empathy",
  "relevance",
  "personalization",
  "context",
  "safety",
  "clarity",
  "usefulness",
] as const

export async function listReviewableMessages(patientId: string): Promise<ReviewableMessage[]> {
  const res = await request<{ items: ReviewableMessage[] }>(`/api/v1/clinician/ai-review/patients/${patientId}/messages`)
  return res.items
}

export type AiReviewDecision = "APPROVE" | "EDIT" | "REJECT" | "FLAG_SAFETY"
export type AiReviewFeedbackCategory =
  | "TONE"
  | "CLINICAL_ACCURACY"
  | "PERSONALIZATION"
  | "CONTEXT_UNDERSTANDING"
  | "SAFETY"
  | "RELEVANCE"
  | "OTHER"

export interface AiReviewSubmission {
  decision: AiReviewDecision
  scores: Record<string, number>
  feedback_category: AiReviewFeedbackCategory
  corrected_response?: string
  clinical_comment?: string
}

export async function submitAiReview(messageId: string, body: AiReviewSubmission): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/v1/clinician/ai-review/messages/${messageId}/review`, {
    method: "POST",
    body: JSON.stringify({ corrected_response: "", clinical_comment: "", ...body }),
  })
}

export interface AiReviewItem {
  id: string
  decision: AiReviewDecision
  scores: Record<string, number>
  feedback_category: string
  corrected_response: string | null
  clinical_comment: string | null
  model_version: string | null
  created_at: string
}

export async function getReviewsForMessage(messageId: string): Promise<AiReviewItem[]> {
  const res = await request<{ items: AiReviewItem[] }>(`/api/v1/clinician/ai-review/messages/${messageId}/reviews`)
  return res.items
}

export interface QualityReport {
  model_version: string | null
  review_count: number
  by_decision: Record<AiReviewDecision, number>
  by_feedback_category: Record<string, number>
  mean_scores: Record<string, number | null>
  approval_rate: number | null
}

export async function getQualityReport(modelVersion?: string, since?: string): Promise<QualityReport> {
  const params = new URLSearchParams()
  if (modelVersion) params.set("model_version", modelVersion)
  if (since) params.set("since", since)
  const qs = params.toString()
  return request<QualityReport>(`/api/v1/clinician/ai-review/quality-report${qs ? `?${qs}` : ""}`)
}

export interface SafetyFlagItem {
  id: string
  message_id: string
  model_version: string | null
  feedback_category: string
  clinical_comment: string | null
  created_at: string
}

export async function getSafetyFlags(since?: string): Promise<SafetyFlagItem[]> {
  const params = new URLSearchParams()
  if (since) params.set("since", since)
  const qs = params.toString()
  const res = await request<{ items: SafetyFlagItem[] }>(`/api/v1/clinician/ai-review/safety-flags${qs ? `?${qs}` : ""}`)
  return res.items
}

// --- Console admin (server/app/api/admin.py) ---

export interface AdminUserItem {
  id: string
  email: string
  display_name: string
  roles: string[]
  status: string
}

export async function listAdminUsers(role?: string): Promise<AdminUserItem[]> {
  const qs = role ? `?role=${encodeURIComponent(role)}` : ""
  const res = await request<{ items: AdminUserItem[] }>(`/api/v1/admin/users${qs}`)
  return res.items
}

export interface RelationshipItem {
  id: string
  patient_id: string
  clinician_id: string
  status: string
  created_at: string
  ended_at: string | null
}

export async function listRelationships(activeOnly = false): Promise<RelationshipItem[]> {
  const res = await request<{ items: RelationshipItem[] }>(
    `/api/v1/admin/relationships${activeOnly ? "?active_only=true" : ""}`,
  )
  return res.items
}

export async function createRelationship(patientId: string, clinicianId: string): Promise<{ id: string }> {
  return request<{ id: string }>("/api/v1/admin/relationships", {
    method: "POST",
    body: JSON.stringify({ patient_id: patientId, clinician_id: clinicianId }),
  })
}

export async function endRelationship(relationshipId: string): Promise<void> {
  await request<void>(`/api/v1/admin/relationships/${relationshipId}`, { method: "DELETE" })
}

export interface ChannelItem {
  id: string
  name: string
  kind: string
  is_active: boolean
  target_hint: string
}

export async function listChannels(): Promise<ChannelItem[]> {
  const res = await request<{ items: ChannelItem[] }>("/api/v1/admin/notification-channels")
  return res.items
}

export async function createChannel(
  name: string,
  kind: "email" | "sms" | "push" | "log",
  target: string,
): Promise<{ id: string }> {
  return request<{ id: string }>("/api/v1/admin/notification-channels", {
    method: "POST",
    body: JSON.stringify({ name, kind, target }),
  })
}

// Miroir des événements yield par `server/app/application/conversation.py::stream_turn`.
export type ConversationEvent =
  | { type: "user_message"; id: string; sequence_no: number; content: string }
  | { type: "assistant_chunk"; text: string }
  | { type: "assistant_correction"; text: string }
  | {
      type: "assistant_message"
      id: string
      sequence_no: number
      content: string
      generation_path: string
      provider: string | null
      decision_level: string
    }
  | { type: "done" }

/**
 * POST + SSE : l'EventSource natif du navigateur ne supporte ni POST ni en-tête
 * Authorization, d'où un lecteur manuel du flux `text/event-stream` via fetch.
 */
export async function streamMessage(
  conversationId: string,
  text: string,
  onEvent: (event: ConversationEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken()
  const headers = new Headers({ "Content-Type": "application/json" })
  if (token) headers.set("Authorization", `Bearer ${token}`)

  const res = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}/messages/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text }),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, await readErrorMessage(res, res.statusText))
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sepIndex = buffer.indexOf("\n\n")
    while (sepIndex !== -1) {
      const rawEvent = buffer.slice(0, sepIndex)
      buffer = buffer.slice(sepIndex + 2)
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data: "))
      if (dataLine) {
        try {
          onEvent(JSON.parse(dataLine.slice("data: ".length)) as ConversationEvent)
        } catch {
          // ligne SSE malformée : ignorée plutôt que d'interrompre tout le flux.
        }
      }
      sepIndex = buffer.indexOf("\n\n")
    }
  }
}
