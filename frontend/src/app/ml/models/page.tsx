import { ModelRegistryPanel } from "@/components/mlops/ModelRegistryPanel"

export default function MlModelsPage() {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-5 py-8 md:px-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Registre de modèles</h1>
        <p className="text-sm text-muted-foreground">
          Gouvernance des versions (ADR-011) — miroir best-effort vers MLflow, jamais bloquant.
        </p>
      </div>
      <ModelRegistryPanel />
    </div>
  )
}
