"use client"

import { Boxes, Cpu, Files, Gauge, Layers } from "lucide-react"

import { BenchmarkChart } from "@/components/insights/benchmark-chart"
import { KnowledgeMap } from "@/components/insights/knowledge-map"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useStats } from "@/lib/api/insights"
import { formatMs, formatNumber, formatPercent } from "@/lib/format"

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Files; label: string; value: string; hint?: string }) {
  return (
    <Card size="sm">
      <CardContent className="flex items-center gap-3">
        <span className="bg-accent text-accent-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-muted-foreground text-xs">{label}</p>
          <p className="truncate text-lg leading-tight font-semibold">{value}</p>
          {hint && <p className="text-muted-foreground truncate text-[0.7rem]">{hint}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

export function InsightsView() {
  const { data, isPending, isError, error, refetch } = useStats()

  return (
    <div className="space-y-8">
      <PageHeader
        title="Insights"
        description="What is in the knowledge base, how retrieval performs, and a 3D look at how your documents relate to each other."
      />

      {isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="Loading statistics">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="border-destructive/40 bg-destructive/5 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm"
        >
          <span className="text-destructive">{error.message}</span>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Stat
              icon={Files}
              label="Documents"
              value={formatNumber(data.documents)}
              hint={
                Object.entries(data.file_types)
                  .map(([t, n]) => `${n} ${t}`)
                  .join(" · ") || undefined
              }
            />
            <Stat icon={Boxes} label="Searchable chunks" value={formatNumber(data.chunks)} />
            <Stat icon={Cpu} label="Language model" value={data.llm_model} hint={data.llm_provider} />
            <Stat
              icon={Layers}
              label="Embeddings"
              value={data.embedding_model.split("/").pop() ?? data.embedding_model}
              hint={data.embedding_provider}
            />
            <Stat
              icon={Gauge}
              label="Evaluated answers"
              value={formatNumber(data.evaluation.count)}
              hint={
                data.evaluation.count
                  ? `overall ${formatPercent(data.evaluation.aggregate.overall)} · ${formatMs(data.evaluation.avg_latency_ms)}`
                  : "none yet"
              }
            />
          </div>

          {data.benchmark ? (
            <BenchmarkChart benchmark={data.benchmark} />
          ) : (
            <p className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
              No retrieval benchmark found. Generate one with <code>python scripts/benchmark_retrieval.py</code> in the
              backend.
            </p>
          )}
        </>
      )}

      <KnowledgeMap />
    </div>
  )
}
