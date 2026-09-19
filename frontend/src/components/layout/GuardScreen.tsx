import Link from "next/link"
import { ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"

export function LoadingScreen() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center">
      <div className="h-10 w-10 animate-pulse rounded-full bg-muted" aria-hidden />
      <span className="sr-only">Chargement</span>
    </div>
  )
}

export function AccessDeniedScreen() {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 px-6 text-center">
      <ShieldAlert className="h-8 w-8 text-muted-foreground" strokeWidth={1.5} />
      <div className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">Accès non autorisé</h1>
        <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
          Votre compte n&apos;a pas les droits nécessaires pour consulter cet espace.
        </p>
      </div>
      <Button asChild variant="outline" size="sm">
        <Link href="/">Retour à l&apos;accueil</Link>
      </Button>
    </div>
  )
}
