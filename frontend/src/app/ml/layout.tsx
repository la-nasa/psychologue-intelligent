"use client"

import { usePathname } from "next/navigation"
import { GraduationCap, Boxes } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { AccessDeniedScreen, LoadingScreen } from "@/components/layout/GuardScreen"
import { type NavItem } from "@/components/layout/Sidebar"
import { useRoleGuard } from "@/lib/useCurrentUser"

const TITLES: Record<string, string> = {
  "/ml": "Apprentissage continu",
  "/ml/models": "Registre de modèles",
}

export default function MlLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { state, me } = useRoleGuard(["ML_ENGINEER", "SUPER_ADMIN"])

  if (state === "loading") return <LoadingScreen />
  if (state === "denied") return <AccessDeniedScreen />

  const navigation: NavItem[] = [
    { name: "Apprentissage", href: "/ml", icon: GraduationCap },
    { name: "Registre de modèles", href: "/ml/models", icon: Boxes },
  ]

  return (
    <AppShell
      navigation={navigation}
      identityName={me?.email ?? null}
      brandSubtitle="Espace MLOps"
      identitySubtitle="Ingénieur ML"
      title={TITLES[pathname]}
    >
      {children}
    </AppShell>
  )
}
