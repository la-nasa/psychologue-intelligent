"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Home, MessageCircle, Mic, History, User } from "lucide-react"
import { cn } from "@/lib/utils"

const TABS = [
  { name: "Accueil", href: "/", icon: Home },
  { name: "Parler", href: "/conversation", icon: MessageCircle },
  { name: "Voix", href: "/voice", icon: Mic },
  { name: "Historique", href: "/history", icon: History },
  { name: "Compte", href: "/profile", icon: User },
] as const

export function MobileTabBar() {
  const pathname = usePathname()

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
      aria-label="Navigation principale"
    >
      <ul className="grid grid-cols-5">
        {TABS.map((tab) => {
          const active = pathname === tab.href || (tab.href !== "/" && pathname.startsWith(tab.href))
          return (
            <li key={tab.href}>
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-12 flex-col items-center justify-center gap-0.5 text-[11px] font-medium tracking-tight",
                  active ? "text-primary" : "text-muted-foreground",
                )}
              >
                <tab.icon className="h-4 w-4" strokeWidth={active ? 2 : 1.5} />
                {tab.name}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
