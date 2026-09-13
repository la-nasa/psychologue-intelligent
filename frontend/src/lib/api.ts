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

export async function listClinicianAlerts(): Promise<ClinicianAlertItem[]> {
  const res = await request<{ items: ClinicianAlertItem[] }>("/api/v1/clinician/alerts")
  return res.items
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
