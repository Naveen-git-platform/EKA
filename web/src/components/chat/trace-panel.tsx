"use client"

import dynamic from "next/dynamic"

import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import type { RunTrace } from "@/lib/chat/types"
import { formatMs, formatPercent } from "@/lib/format"

// React Flow is only needed once someone opens the trace, so keep it out of the initial chat bundle.
const TraceGraph = dynamic(() => import("@/components/chat/trace-graph"), {
  ssr: false,
  loading: () => <Skeleton className="h-44 w-full rounded-xl" />,
})

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h4 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{title}</h4>
      {children}
    </section>
  )
}

function QueryList({ queries }: { queries: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {queries.map((q) => (
        <li key={q} className="bg-muted rounded-md px-2 py-1 text-xs">
          {q}
        </li>
      ))}
    </ul>
  )
}

type Props = { run: RunTrace | undefined; streaming: boolean }

export function TracePanel({ run, streaming }: Props) {
  return (
    <div className="space-y-4 rounded-xl border p-3" data-testid="trace-panel">
      <TraceGraph run={run} streaming={streaming} />

      {run?.plan && (
        <Section title="Plan">
          <p className="text-sm">
            <Badge variant="secondary" className="mr-2">
              {run.plan.strategy.replace("_", " ")}
            </Badge>
            {run.plan.fallback && <Badge variant="outline">fallback plan</Badge>}
          </p>
          {run.plan.reasoning && <p className="text-muted-foreground text-sm">{run.plan.reasoning}</p>}
          <QueryList queries={run.plan.sub_queries} />
        </Section>
      )}

      {run?.retrievals.map((r, i) => (
        <Section key={r.iteration + "-" + i} title={`Retrieval pass ${i + 1} · ${r.total} chunks`}>
          <QueryList queries={r.queries} />
          <ul className="divide-y rounded-lg border text-xs">
            {r.chunks.slice(0, 6).map((c) => (
              <li key={c.chunk_id} className="flex items-center gap-2 px-2 py-1.5">
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{c.filename ?? "document"}</span>
                  <span className="text-muted-foreground">
                    {c.page ? ` · p.${c.page}` : ""}
                    {c.section ? ` · ${c.section}` : ""}
                  </span>
                </span>
                {c.sources.map((s) => (
                  <Badge key={s} variant="outline" className="h-4 px-1.5 text-[0.65rem]">
                    {s}
                  </Badge>
                ))}
                <span className="text-muted-foreground tabular-nums">{c.score.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </Section>
      ))}

      {run?.critiques.map((c, i) => (
        <Section key={c.iteration + "-" + i} title={`Critic review ${i + 1}`}>
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant={c.sufficient ? "default" : "secondary"}>
              {c.sufficient ? "Sufficient" : "Insufficient"}
            </Badge>
            <span className="text-muted-foreground text-xs">
              confidence {formatPercent(c.confidence)} · relevance {formatPercent(c.relevance)} · coverage{" "}
              {formatPercent(c.coverage)}
            </span>
            {c.degraded && <Badge variant="outline">critic unavailable</Badge>}
          </p>
          {c.reasoning && <p className="text-muted-foreground text-sm">{c.reasoning}</p>}
          {c.will_retry && c.rewritten_queries.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs">Searched again with:</p>
              <QueryList queries={c.rewritten_queries} />
            </div>
          )}
        </Section>
      ))}

      {run?.done && (
        <Section title="Timing">
          <ul className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {run.done.trace.map((t, i) => (
              <li key={`${t.node}-${i}`}>
                {t.node} <span className="text-foreground tabular-nums">{formatMs(t.ms)}</span>
              </li>
            ))}
            <li>
              total <span className="text-foreground tabular-nums">{formatMs(run.done.elapsed_ms)}</span>
            </li>
          </ul>
        </Section>
      )}

      {run && run.errors.length > 0 && (
        <Section title="Problems">
          <ul className="text-destructive space-y-1 text-xs">
            {run.errors.map((e, i) => (
              <li key={i}>
                <strong>{e.stage}:</strong> {e.message}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}
