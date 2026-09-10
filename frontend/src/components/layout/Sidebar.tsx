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
  Activity,
  FileText,
  Bell,
  Shield
} from "lucide-react"

const navigation = [
  { name: "Accueil", href: "/", icon: Home },
  { name: "Conversation", href: "/conversation", icon: MessageCircle },
  { name: "Voix", href: "/voice", icon: Mic },
  { name: "Objectifs", href: "/goals", icon: Activity },
  { name: "Historique", href: "/history", icon: FileText },
  { name: "Alertes", href: "/alerts", icon: Bell },
  { name: "Profil", href: "/profile", icon: User },
  { name: "Paramètres", href: "/settings", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <div className="flex h-full w-64 flex-col border-r bg-background">
      <div className="flex h-14 items-center border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Shield className="h-6 w-6 text-primary" />
          <span>Psychologue IA</span>
        </Link>
      </div>
      <div className="flex-1 overflow-auto py-4">
        <nav className="grid gap-1 px-2">
          {navigation.map((item) => {
            const isActive = pathname === item.href
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </Link>
            )
          })}
        </nav>
      </div>
      <div className="border-t p-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
            <User className="h-4 w-4 text-primary" />
          </div>
          <div className="text-sm">
            <p className="font-medium">Utilisateur</p>
            <p className="text-xs text-muted-foreground">En ligne</p>
          </div>
        </div>
      </div>
    </div>
  )
}
