const STORAGE_KEY = "mensana-a11y"

export type A11yPrefs = {
  highContrast: boolean
  largeText: boolean
  reducedMotion: boolean
}

export const DEFAULT_A11Y: A11yPrefs = {
  highContrast: false,
  largeText: false,
  reducedMotion: false,
}

export function getA11yPrefs(): A11yPrefs {
  if (typeof window === "undefined") return DEFAULT_A11Y
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_A11Y
    const parsed = JSON.parse(raw) as Partial<A11yPrefs>
    return { ...DEFAULT_A11Y, ...parsed }
  } catch {
    return DEFAULT_A11Y
  }
}

export function applyA11yPrefs(prefs: A11yPrefs): void {
  const root = document.documentElement
  root.classList.toggle("high-contrast", prefs.highContrast)
  root.classList.toggle("large-text", prefs.largeText)
  root.classList.toggle("reduce-motion", prefs.reducedMotion)
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // Navigation privée : classes valables pour la session uniquement.
  }
}
