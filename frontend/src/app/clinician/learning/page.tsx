import { LearningReviewPanel } from "@/components/learning/LearningReviewPanel"

export default function ClinicianLearningPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-8 md:py-10">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Apprentissage continu</h1>
        <p className="text-sm text-muted-foreground">
          Revue clinique des échantillons — approbation double requise (clinique + technique) avant toute promotion.
        </p>
      </div>
      <LearningReviewPanel canPromote />
    </div>
  )
}
