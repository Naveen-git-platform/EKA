import type { Metadata } from "next"

import { EvaluationView } from "@/components/evaluation/evaluation-view"

export const metadata: Metadata = { title: "Evaluation" }

export default function EvaluationPage() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6">
      <EvaluationView />
    </div>
  )
}
