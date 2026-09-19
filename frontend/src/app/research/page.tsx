import { AnalyticsPanel } from "@/components/analytics/AnalyticsPanel"

export default function ResearchPage() {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-5 py-8 md:px-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-muted-foreground">Données dé-identifiées uniquement — pseudonymes rotatifs, jamais l'identité du patient.</p>
      </div>
      <AnalyticsPanel />
    </div>
  )
}
