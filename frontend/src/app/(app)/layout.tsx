"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { Sidebar } from "@/components/layout/Sidebar"
import { Header } from "@/components/layout/Header"
import { getProfile, getToken } from "@/lib/api"

const TITLES: Record<string, string> = {
  "/conversation": "Conversation",
  "/voice": "Voix",
  "/checkin": "Check-in rapide",
  "/goals": "Objectifs",
  "/history": "Historique",
  "/alerts": "Alertes",
  "/profile": "Profil",
  "/settings": "Paramètres",
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [patientName, setPatientName] = useState<string | null>(null)

  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  useEffect(() => {
    if (!getToken()) return
    getProfile()
      .then((p) => setPatientName(p.display_name || null))
      .catch(() => {})
  }, [pathname])

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar — fixe sur desktop, tiroir sur mobile */}
      <div className="hidden md:block">
        <Sidebar patientName={patientName} />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-foreground/20 backdrop-blur-[1px]"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="relative h-full w-64 shadow-soft-lg">
            <Sidebar patientName={patientName} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title={TITLES[pathname]} onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
