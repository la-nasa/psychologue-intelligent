const STORAGE_KEY = "mensana-theme"

export type Theme = "light" | "dark"

export function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === "light" || value === "dark" ? value : null
  } catch {
    return null
  }
}

export function getEffectiveTheme(): Theme {
  const stored = getStoredTheme()
  if (stored) return stored
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark"
  }
  return "light"
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.classList.remove("light", "dark")
  root.classList.add(theme)
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Préférence non persistée (navigation privée) — reste valable pour la session.
  }
}
