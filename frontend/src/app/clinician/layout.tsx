"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { LayoutDashboard, Users, BellRing, ClipboardCheck, LineChart } from "lucide-react"
import { Sidebar, type NavItem } from "@/components/layout/Sidebar"
import { Header } from "@/components/layout/Header"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { useRoleGuard } from "@/lib/useCurrentUser"

const TITLES: Record<string, string> = {
  "/clinician": "Vue d'ensemble",
  "/clinician/patients": "Patients suivis",
  "/clinician/alerts": "Centre d'alertes",
  "/clinician/review": "Revue des réponses IA",
  "/clinician/quality": "Qualité du modèle",
}

function titleFor(pathname: string): string | undefined {
  if (TITLES[pathname]) return TITLES[pathname]
  if (pathname.startsWith("/clinician/patients/")) return "Dossier patient"
  return undefined
}

export default function ClinicianLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { state, me } = useRoleGuard(["PSYCHOLOGIST", "CLINICAL_SUPERVISOR"])

  useEffect(() => setMobileOpen(false), [pathname])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const isSupervisor = me?.roles.includes("CLINICAL_SUPERVISOR")
  const navigation: NavItem[] = [
    { name: "Vue d'ensemble", href: "/clinician", icon: LayoutDashboard },
    { name: "Patients", href: "/clinician/patients", icon: Users },
    { name: "Alertes", href: "/clinician/alerts", icon: BellRing },
    { name: "Revue IA", href: "/clinician/review", icon: ClipboardCheck },
    ...(isSupervisor ? [{ name: "Qualité", href: "/clinician/quality", icon: LineChart }] : []),
  ]

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden md:block">
        <Sidebar
          navigation={navigation}
          accountNavigation={[]}
          patientName={me?.email ?? null}
          brandSubtitle="Espace clinicien"
          identitySubtitle={isSupervisor ? "Superviseur clinique" : "Psychologue"}
        />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-foreground/20 backdrop-blur-[1px]" onClick={() => setMobileOpen(false)} aria-hidden />
          <div className="relative h-full w-64 shadow-soft-lg">
            <Sidebar
              navigation={navigation}
              accountNavigation={[]}
              patientName={me?.email ?? null}
              brandSubtitle="Espace clinicien"
              identitySubtitle={isSupervisor ? "Superviseur clinique" : "Psychologue"}
              onNavigate={() => setMobileOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title={titleFor(pathname)} onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
