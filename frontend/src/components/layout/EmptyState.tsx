import Link from "next/link"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionHref,
  actionLabel,
  className,
}: {
  icon: LucideIcon
  title: string
  description: string
  actionHref?: string
  actionLabel?: string
  className?: string
}) {
  return (
    <div className={cn("flex flex-col items-center gap-3 px-6 py-14 text-center", className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full border bg-muted/50">
        <Icon className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
      </div>
      <div className="max-w-sm space-y-1">
        <p className="text-sm font-medium tracking-tight">{title}</p>
        <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
      </div>
      {actionHref && actionLabel && (
        <Button asChild variant="outline" size="sm" className="mt-1">
          <Link href={actionHref}>{actionLabel}</Link>
        </Button>
      )}
    </div>
  )
}

export function AuthGate({ message }: { message: string }) {
  return (
    <div className="flex min-h-[60dvh] flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">{message}</p>
      <Button asChild>
        <Link href="/login">Se connecter</Link>
      </Button>
    </div>
  )
}

export function PageSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-3 px-5 py-8 md:px-8" aria-hidden>
      <div className="h-7 w-48 animate-pulse rounded-md bg-muted" />
      <div className="h-4 w-72 animate-pulse rounded-md bg-muted" />
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-xl bg-muted/70" />
      ))}
    </div>
  )
}
