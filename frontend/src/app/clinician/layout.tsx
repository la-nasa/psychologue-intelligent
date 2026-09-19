"use client"

import { usePathname } from "next/navigation"
import { LayoutDashboard, Users, BellRing, ClipboardCheck, LineChart, GraduationCap } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { type NavItem } from "@/components/layout/Sidebar"
import { useRoleGuard } from "@/lib/useCurrentUser"

const TITLES: Record<string, string> = {
  "/clinician": "Vue d'ensemble",
  "/clinician/patients": "Patients suivis",
  "/clinician/alerts": "Centre d'alertes",
  "/clinician/review": "Revue des réponses IA",
  "/clinician/learning": "Apprentissage continu",
  "/clinician/quality": "Qualité du modèle",
}

function titleFor(pathname: string): string | undefined {
  if (TITLES[pathname]) return TITLES[pathname]
  if (pathname.startsWith("/clinician/patients/")) return "Dossier patient"
  return undefined
}

export default function ClinicianLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { state, me } = useRoleGuard(["PSYCHOLOGIST", "CLINICAL_SUPERVISOR"])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const isSupervisor = me?.roles.includes("CLINICAL_SUPERVISOR")
  const navigation: NavItem[] = [
    { name: "Vue d'ensemble", href: "/clinician", icon: LayoutDashboard },
    { name: "Patients", href: "/clinician/patients", icon: Users },
    { name: "Alertes", href: "/clinician/alerts", icon: BellRing },
    { name: "Revue IA", href: "/clinician/review", icon: ClipboardCheck },
    { name: "Apprentissage", href: "/clinician/learning", icon: GraduationCap },
    ...(isSupervisor ? [{ name: "Qualité", href: "/clinician/quality", icon: LineChart }] : []),
  ]

  return (
    <AppShell
      navigation={navigation}
      identityName={me?.email ?? null}
      brandSubtitle="Espace clinicien"
      identitySubtitle={isSupervisor ? "Superviseur clinique" : "Psychologue"}
      title={titleFor(pathname)}
    >
      {children}
    </AppShell>
  )
}
