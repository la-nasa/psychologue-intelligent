"use client"

import { BarChart3 } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { type NavItem } from "@/components/layout/Sidebar"
import { useRoleGuard } from "@/lib/useCurrentUser"

export default function ResearchLayout({ children }: { children: React.ReactNode }) {
  const { state, me } = useRoleGuard(["RESEARCHER", "ADMIN", "SUPER_ADMIN"])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const navigation: NavItem[] = [{ name: "Analytics", href: "/research", icon: BarChart3 }]

  return (
    <AppShell
      navigation={navigation}
      identityName={me?.email ?? null}
      brandSubtitle="Espace recherche"
      identitySubtitle="Chercheur"
      title="Analytics"
    >
      {children}
    </AppShell>
  )
}
