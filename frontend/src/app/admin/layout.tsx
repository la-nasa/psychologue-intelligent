"use client"

import { usePathname } from "next/navigation"
import { Users, Link2, BellRing, LineChart, BarChart3 } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { type NavItem } from "@/components/layout/Sidebar"
import { useRoleGuard } from "@/lib/useCurrentUser"

const TITLES: Record<string, string> = {
  "/admin": "Relations patient-clinicien",
  "/admin/channels": "Canaux de notification",
  "/admin/directory": "Annuaire",
  "/admin/analytics": "Analytics",
  "/admin/quality": "Qualité du modèle",
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { state, me } = useRoleGuard(["ADMIN", "SUPER_ADMIN"])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const isSuperAdmin = me?.roles.includes("SUPER_ADMIN")
  const navigation: NavItem[] = [
    { name: "Relations", href: "/admin", icon: Link2 },
    { name: "Notifications", href: "/admin/channels", icon: BellRing },
    { name: "Annuaire", href: "/admin/directory", icon: Users },
    { name: "Analytics", href: "/admin/analytics", icon: BarChart3 },
    ...(isSuperAdmin ? [{ name: "Qualité IA", href: "/admin/quality", icon: LineChart }] : []),
  ]

  return (
    <AppShell
      navigation={navigation}
      identityName={me?.email ?? null}
      brandSubtitle="Console admin"
      identitySubtitle={isSuperAdmin ? "Super-admin" : "Administrateur"}
      title={TITLES[pathname]}
    >
      {children}
    </AppShell>
  )
}
