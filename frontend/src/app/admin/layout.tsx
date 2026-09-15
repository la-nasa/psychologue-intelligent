"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { Users, Link2, BellRing, LineChart } from "lucide-react"
import { Sidebar, type NavItem } from "@/components/layout/Sidebar"
import { Header } from "@/components/layout/Header"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { useRoleGuard } from "@/lib/useCurrentUser"

const TITLES: Record<string, string> = {
  "/admin": "Relations patient-clinicien",
  "/admin/channels": "Canaux de notification",
  "/admin/directory": "Annuaire",
  "/admin/quality": "Qualité du modèle",
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { state, me } = useRoleGuard(["ADMIN", "SUPER_ADMIN"])

  useEffect(() => setMobileOpen(false), [pathname])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const isSuperAdmin = me?.roles.includes("SUPER_ADMIN")
  const navigation: NavItem[] = [
    { name: "Relations", href: "/admin", icon: Link2 },
    { name: "Notifications", href: "/admin/channels", icon: BellRing },
    { name: "Annuaire", href: "/admin/directory", icon: Users },
    ...(isSuperAdmin ? [{ name: "Qualité IA", href: "/admin/quality", icon: LineChart }] : []),
  ]

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden md:block">
        <Sidebar
          navigation={navigation}
          accountNavigation={[]}
          patientName={me?.email ?? null}
          brandSubtitle="Console admin"
          identitySubtitle={isSuperAdmin ? "Super-admin" : "Administrateur"}
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
              brandSubtitle="Console admin"
              identitySubtitle={isSuperAdmin ? "Super-admin" : "Administrateur"}
              onNavigate={() => setMobileOpen(false)}
            />
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
