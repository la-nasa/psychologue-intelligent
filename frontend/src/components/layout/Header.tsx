"use client"

import * as React from "react"
import { Menu, Sun, Moon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { applyTheme, getEffectiveTheme, type Theme } from "@/lib/theme"

interface HeaderProps {
  title?: string
  onMenuClick?: () => void
}

export function Header({ title, onMenuClick }: HeaderProps) {
  const [theme, setThemeState] = React.useState<Theme | null>(null)

  React.useEffect(() => {
    setThemeState(getEffectiveTheme())
  }, [])

  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark"
    applyTheme(next)
    setThemeState(next)
  }

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border/80 bg-background/75 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/55 md:px-6">
      <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenuClick} aria-label="Ouvrir le menu">
        <Menu className="h-5 w-5" strokeWidth={1.5} />
      </Button>

      <div className="flex-1">
        {title && <p className="text-sm font-medium tracking-tight text-muted-foreground">{title}</p>}
      </div>

      <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Changer de thème">
        {theme === "dark" ? (
          <Sun className="h-[18px] w-[18px]" strokeWidth={1.5} />
        ) : (
          <Moon className="h-[18px] w-[18px]" strokeWidth={1.5} />
        )}
      </Button>
    </header>
  )
}
