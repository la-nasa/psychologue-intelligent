"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { AppShell } from "@/components/layout/AppShell"
import { patientAccountNavigation, patientNavigation } from "@/components/layout/Sidebar"
import { getProfile, getToken } from "@/lib/api"

const TITLES: Record<string, string> = {
  "/conversation": "Conversation",
  "/voice": "Voix",
  "/checkin": "Check-in",
  "/goals": "Objectifs",
  "/history": "Historique",
  "/profile": "Profil",
  "/settings": "Paramètres",
}

function titleFor(pathname: string): string | undefined {
  if (pathname === "/") return undefined
  if (TITLES[pathname]) return TITLES[pathname]
  if (pathname.startsWith("/history/")) return "Conversation"
  return undefined
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [patientName, setPatientName] = useState<string | null>(null)

  useEffect(() => {
    if (!getToken()) return
    getProfile()
      .then((p) => setPatientName(p.display_name || null))
      .catch(() => {})
  }, [pathname])

  return (
    <AppShell
      navigation={patientNavigation}
      accountNavigation={patientAccountNavigation}
      identityName={patientName}
      identitySubtitle="Espace personnel"
      title={titleFor(pathname)}
      showMobileTabs
    >
      {children}
    </AppShell>
  )
}
