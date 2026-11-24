import type { Metadata } from "next"

import { InsightsView } from "@/components/insights/insights-view"

export const metadata: Metadata = { title: "Insights" }

export default function InsightsPage() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6">
      <InsightsView />
    </div>
  )
}
