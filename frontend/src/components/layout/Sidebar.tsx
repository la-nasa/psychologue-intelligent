"use client"

import * as React from "react"
import {
  Home,
  MessageCircle,
  Mic,
  Settings,
  User,
  Target,
  History,
  Activity,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  name: string
  href: string
  icon: LucideIcon
}

export const patientNavigation: NavItem[] = [
  { name: "Accueil", href: "/", icon: Home },
  { name: "Conversation", href: "/conversation", icon: MessageCircle },
  { name: "Voix", href: "/voice", icon: Mic },
  { name: "Check-in", href: "/checkin", icon: Activity },
  { name: "Objectifs", href: "/goals", icon: Target },
  { name: "Historique", href: "/history", icon: History },
]

export const patientAccountNavigation: NavItem[] = [
  { name: "Profil", href: "/profile", icon: User },
  { name: "Paramètres", href: "/settings", icon: Settings },
]
