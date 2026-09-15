"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import {
  Home,
  MessageCircle,
  Mic,
  Settings,
  User,
  Target,
  History,
  BellRing,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  name: string
  href: string
  icon: LucideIcon
}

const navigation: NavItem[] = [
  { name: "Accueil", href: "/", icon: Home },
  { name: "Conversation", href: "/conversation", icon: MessageCircle },
  { name: "Voix", href: "/voice", icon: Mic },
  { name: "Objectifs", href: "/goals", icon: Target },
  { name: "Historique", href: "/history", icon: History },
  { name: "Alertes", href: "/alerts", icon: BellRing },
]

const accountNavigation: NavItem[] = [
  { name: "Profil", href: "/profile", icon: User },
  { name: "Paramètres", href: "/settings", icon: Settings },
]

interface SidebarProps {
  onNavigate?: () => void
  patientName?: string | null
  navigation?: NavItem[]
  accountNavigation?: NavItem[]
  brandSubtitle?: string
  identitySubtitle?: string
}

function NavList({ items, pathname, onNavigate }: { items: NavItem[]; pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="grid gap-0.5 px-3">
      {items.map((item) => {
        const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`))
        return (
          <Link
            key={item.name}
            href={item.href}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium tracking-tight transition-colors",
              isActive
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
            )}
          >
            <span
              className={cn(
                "absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary transition-opacity",
                isActive ? "opacity-100" : "opacity-0"
              )}
              aria-hidden
            />
            <item.icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
            {item.name}
          </Link>
        )
      })}
    </nav>
  )
}

export function Sidebar({
  onNavigate,
  patientName,
  navigation: navOverride,
  accountNavigation: accountOverride,
  brandSubtitle,
  identitySubtitle,
}: SidebarProps) {
  const pathname = usePathname()
  const mainItems = navOverride ?? navigation
  const accountItems = accountOverride ?? accountNavigation

  return (
    <div className="flex h-full w-64 flex-col border-r bg-card">
      <div className="flex h-16 flex-col justify-center border-b px-5">
        <Link href="/" className="flex items-baseline gap-2" onClick={onNavigate}>
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
          <span className="text-base font-semibold tracking-tight">Mensana</span>
        </Link>
        {brandSubtitle && <span className="ml-3.5 text-[11px] text-muted-foreground">{brandSubtitle}</span>}
      </div>
      <div className="flex-1 overflow-auto py-5">
        <NavList items={mainItems} pathname={pathname} onNavigate={onNavigate} />
        {accountItems.length > 0 && (
          <>
            <div className="mx-5 my-4 border-t" />
            <NavList items={accountItems} pathname={pathname} onNavigate={onNavigate} />
          </>
        )}
      </div>
      <div className="border-t p-4">
        <div className="flex items-center gap-3 rounded-md px-1 py-1">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-medium text-accent-foreground">
            {(patientName || "?").slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium leading-tight">{patientName || "Votre espace"}</p>
            <p className="text-xs text-muted-foreground">{identitySubtitle ?? "Connecté"}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
