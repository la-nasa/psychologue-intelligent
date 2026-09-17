"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { GraduationCap, Boxes } from "lucide-react"
import { Sidebar, type NavItem } from "@/components/layout/Sidebar"
import { Header } from "@/components/layout/Header"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { useRoleGuard } from "@/lib/useCurrentUser"

const TITLES: Record<string, string> = {
  "/ml": "Apprentissage continu",
  "/ml/models": "Registre de modèles",
}

export default function MlLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { state, me } = useRoleGuard(["ML_ENGINEER", "SUPER_ADMIN"])

  useEffect(() => setMobileOpen(false), [pathname])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const navigation: NavItem[] = [
    { name: "Apprentissage", href: "/ml", icon: GraduationCap },
    { name: "Registre de modèles", href: "/ml/models", icon: Boxes },
  ]

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden md:block">
        <Sidebar
          navigation={navigation}
          accountNavigation={[]}
          patientName={me?.email ?? null}
          brandSubtitle="Espace MLOps"
          identitySubtitle="Ingénieur ML"
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
              brandSubtitle="Espace MLOps"
              identitySubtitle="Ingénieur ML"
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
