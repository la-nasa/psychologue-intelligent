import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 px-6 text-center">
      <span className="text-sm font-medium tracking-tight text-primary">Mensana</span>
      <h1 className="text-2xl font-semibold tracking-tight">Cette page n&apos;existe pas</h1>
      <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
        Le lien est peut-être incorrect ou la page a été déplacée.
      </p>
      <Button asChild className="mt-2">
        <Link href="/">Retour à l&apos;accueil</Link>
      </Button>
    </div>
  )
}
