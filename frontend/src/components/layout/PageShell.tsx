import { cn } from "@/lib/utils"

export function PageShell({
  children,
  className,
  wide = false,
  flush = false,
}: {
  children: React.ReactNode
  className?: string
  wide?: boolean
  flush?: boolean
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full",
        wide ? "max-w-5xl" : "max-w-3xl",
        flush ? "flex h-full min-h-0 flex-col" : "space-y-8 px-5 py-8 pb-24 md:px-8 md:py-10 md:pb-10",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-[65ch] space-y-1.5">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
        {description && <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  )
}
