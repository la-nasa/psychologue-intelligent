import { AnalyticsPanel } from "@/components/analytics/AnalyticsPanel"

export default function AdminAnalyticsPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-muted-foreground">Usage produit, séparé et gouverné indépendamment du clinique.</p>
      </div>
      <AnalyticsPanel />
    </div>
  )
}
