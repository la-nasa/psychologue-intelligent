import { QualityPanel } from "@/components/clinician/QualityPanel"

export default function ClinicianQualityPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Qualité du modèle</h1>
        <p className="text-sm text-muted-foreground">Agrégé par version de modèle uniquement — jamais par relecteur.</p>
      </div>
      <QualityPanel />
    </div>
  )
}
