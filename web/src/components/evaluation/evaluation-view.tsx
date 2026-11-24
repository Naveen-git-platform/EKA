"use client"

import { AlertTriangle, BarChart3, Loader2 } from "lucide-react"
import { useMemo, useState } from "react"

import { CategoryBars, ScoreRadar, ScoreTimeline } from "@/components/evaluation/charts"
import { KpiCards } from "@/components/evaluation/kpi-cards"
import { ResultDetailsSheet } from "@/components/evaluation/result-details-sheet"
import { ResultsTable } from "@/components/evaluation/results-table"
import { RunBatchDialog } from "@/components/evaluation/run-batch-dialog"
import { RunsTable } from "@/components/evaluation/runs-table"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocuments } from "@/lib/api/documents"
import { isRunning, useEvaluations, useRuns } from "@/lib/api/evaluation"
import type { EvaluationResult } from "@/lib/api/schemas"
import { countByHealth } from "@/lib/eval/metrics"

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)

export function EvaluationView() {
  const [runId, setRunId] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [detail, setDetail] = useState<EvaluationResult | null>(null)

  const runs = useRuns()
  const running = isRunning(runs.data?.runs, runId)
  const evaluations = useEvaluations(runId, running)
  const docs = useDocuments()

  const results = useMemo(() => evaluations.data?.results ?? [], [evaluations.data])
  const health = useMemo(() => countByHealth(results), [results])
  const avgLatency = useMemo(
    () => mean(results.map((r) => r.latency_ms).filter((v): v is number => typeof v === "number")),
    [results],
  )
  const activeRun = runs.data?.runs.find((r) => r.run_id === runId)
  const noDocs = docs.data !== undefined && docs.data.total === 0

  const scope = (
    <div className="flex items-center gap-2">
      <label htmlFor="scope" className="text-muted-foreground text-sm">
        Show
      </label>
      <select
        id="scope"
        value={runId ?? ""}
        onChange={(e) => setRunId(e.target.value || null)}
        className="bg-background h-8 max-w-56 rounded-lg border px-2 text-sm"
      >
        <option value="">All results</option>
        {runs.data?.runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {r.name || r.run_id}
          </option>
        ))}
      </select>
    </div>
  )

  const loading = evaluations.isPending || runs.isPending
  const failed = evaluations.isError || runs.isError
  const error = evaluations.error ?? runs.error
  const isEmpty = !loading && !failed && (evaluations.data?.total ?? 0) === 0 && (runs.data?.runs.length ?? 0) === 0

  return (
    <div className="space-y-8">
      <PageHeader
        title="Evaluation"
        description="How good are the answers? Four standard RAG metrics, scored by an AI judge, for every run and every answer you chose to score."
        actions={
          <>
            {scope}
            <RunBatchDialog
              open={dialogOpen}
              onOpenChange={setDialogOpen}
              disabledReason={noDocs ? "Add documents first" : undefined}
              onStarted={(run) => setRunId(run.run_id)}
            />
          </>
        }
      />

      {running && activeRun && (
        <div role="status" className="bg-accent/40 flex items-center gap-3 rounded-xl border p-3 text-sm">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          <span>
            <strong>{activeRun.name || activeRun.run_id}</strong> is running: {activeRun.completed} of {activeRun.total}{" "}
            answers scored.
          </span>
        </div>
      )}

      {loading ? (
        <div className="space-y-4" aria-label="Loading evaluations">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : failed ? (
        <div
          role="alert"
          className="border-destructive/40 bg-destructive/5 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm"
        >
          <span className="text-destructive">{error?.message}</span>
          <Button variant="outline" size="sm" onClick={() => void Promise.all([runs.refetch(), evaluations.refetch()])}>
            Retry
          </Button>
        </div>
      ) : isEmpty ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border p-10 text-center">
          <span className="bg-muted text-muted-foreground flex size-11 items-center justify-center rounded-full">
            <BarChart3 className="size-5" aria-hidden />
          </span>
          <div className="space-y-1">
            <h2 className="font-medium">Nothing has been evaluated yet</h2>
            <p className="text-muted-foreground max-w-md text-sm">
              Run the sample questions to see how the agent scores, or turn on “Score answers in the background” in the
              chat options to evaluate your own conversations.
            </p>
          </div>
          {noDocs && <p className="text-warning text-sm">Add documents first, then come back.</p>}
        </div>
      ) : (
        <>
          {health.failed + health.partial > 0 && (
            <div
              role="note"
              className="border-warning/40 bg-warning/10 flex items-start gap-2 rounded-xl border p-3 text-sm"
            >
              <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                {health.failed > 0 && (
                  <>
                    {health.failed} of {results.length} results could not be scored at all.{" "}
                  </>
                )}
                {health.partial > 0 && <>{health.partial} had a metric missing or an error. </>}
                Open a row marked with a warning icon to see what went wrong; unscored metrics are left out of the
                averages rather than counted as zero.
              </span>
            </div>
          )}

          <KpiCards aggregate={evaluations.data?.aggregate} count={results.length} avgLatencyMs={avgLatency} />

          <div className="grid gap-4 lg:grid-cols-3">
            <ScoreRadar aggregate={evaluations.data?.aggregate} />
            <ScoreTimeline results={results} />
            <CategoryBars results={results} />
          </div>

          <section className="space-y-3" aria-labelledby="runs-heading">
            <h2 id="runs-heading" className="text-lg font-semibold">
              Runs
            </h2>
            <RunsTable runs={runs.data?.runs ?? []} selectedId={runId} onSelect={setRunId} />
          </section>

          <section className="space-y-3" aria-labelledby="results-heading">
            <h2 id="results-heading" className="text-lg font-semibold">
              Answers {runId ? "in this run" : ""}
            </h2>
            <ResultsTable results={results} onOpen={setDetail} />
          </section>
        </>
      )}

      <ResultDetailsSheet result={detail} onClose={() => setDetail(null)} />
    </div>
  )
}
