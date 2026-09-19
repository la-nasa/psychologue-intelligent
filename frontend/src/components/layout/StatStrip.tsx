import { cn } from "@/lib/utils"

export function StatStrip({
  items,
}: {
  items: { label: string; value: string | number; tone?: "default" | "danger" | "warning" }[]
}) {
  return (
    <div className={cn("grid grid-cols-1 divide-y rounded-2xl border bg-card sm:divide-x sm:divide-y-0", items.length >= 4 ? "sm:grid-cols-2 lg:grid-cols-4" : items.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}>
      {items.map((item) => (
        <div key={item.label} className="px-5 py-4">
          <p className="text-xs font-medium tracking-wide text-muted-foreground">{item.label}</p>
          <p
            className={cn(
              "mt-1 font-mono text-2xl font-medium tabular-nums tracking-tight",
              item.tone === "danger" && "text-destructive",
              item.tone === "warning" && "text-warning",
            )}
          >
            {item.value}
          </p>
        </div>
      ))}
    </div>
  )
}
