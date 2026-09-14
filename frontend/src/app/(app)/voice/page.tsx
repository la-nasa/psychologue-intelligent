"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Mic, MessageCircle } from "lucide-react"

export default function VoicePage() {
  return (
    <div className="mx-auto flex h-full w-full max-w-lg flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border bg-accent/40">
        <Mic className="h-6 w-6 text-muted-foreground" strokeWidth={1.5} />
      </div>
      <h1 className="text-xl font-semibold tracking-tight">Les sessions vocales arrivent bientôt</h1>
      <p className="text-sm text-muted-foreground">
        Nous construisons une expérience vocale fluide et sécurisée, avec les mêmes garanties de confidentialité
        que la conversation écrite. Elle n&apos;est pas encore disponible — plutôt qu&apos;une démonstration
        factice, nous préférons vous le dire clairement.
      </p>
      <Button asChild className="mt-2">
        <Link href="/conversation">
          <MessageCircle className="h-4 w-4" strokeWidth={1.75} />
          Continuer par écrit
        </Link>
      </Button>
    </div>
  )
}
