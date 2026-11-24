import { FeatureGrid } from "@/components/overview/feature-grid"
import { SystemStatusCard } from "@/components/overview/system-status-card"

export default function OverviewPage() {
  return (
    <div className="relative">
      <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 h-96" aria-hidden />
      <div className="relative mx-auto flex max-w-6xl flex-col gap-10 px-4 py-12 sm:px-6 sm:py-16">
        <section className="max-w-3xl space-y-5">
          <p className="bg-card/60 text-muted-foreground inline-flex items-center rounded-full border px-3 py-1 text-xs">
            Multi-agent RAG · hybrid retrieval · built-in evaluation
          </p>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Ask your documents. <span className="text-gradient">Get answers you can verify.</span>
          </h1>
          <p className="text-muted-foreground text-lg">
            The Enterprise Knowledge Agent plans, retrieves, critiques and cites. Every answer shows its evidence and
            how good it is.
          </p>
        </section>

        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <FeatureGrid />
          <SystemStatusCard />
        </div>
      </div>
    </div>
  )
}
