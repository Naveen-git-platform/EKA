"use client"

import { AlertTriangle } from "lucide-react"

import { ScorePill } from "@/components/evaluation/score-pill"
import { Badge } from "@/components/ui/badge"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { METRIC_NAMES, type EvaluationResult } from "@/lib/api/schemas"
import { METRIC_HELP, METRIC_LABELS } from "@/lib/eval/metrics"
import { formatDateTime, formatMs } from "@/lib/format"

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{title}</h3>
      {children}
    </section>
  )
}

type Props = { result: EvaluationResult | null; onClose: () => void }

export function ResultDetailsSheet({ result, onClose }: Props) {
  return (
    <Sheet open={result !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-xl">
        {result && (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="text-base leading-snug">{result.question}</SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary">{result.source}</Badge>
                {result.category && <Badge variant="outline">{result.category}</Badge>}
                <span className="text-xs">
                  {formatDateTime(result.created_at)} · {formatMs(result.latency_ms)}
                </span>
              </SheetDescription>
            </SheetHeader>

            <div className="flex-1 space-y-5 overflow-y-auto p-4 text-sm">
              {result.errors.length > 0 && (
                <div role="alert" className="border-warning/40 bg-warning/10 space-y-1 rounded-lg border p-3">
                  <p className="flex items-center gap-1.5 font-medium">
                    <AlertTriangle className="text-warning size-4" aria-hidden /> Problems while scoring
                  </p>
                  <ul className="text-muted-foreground list-disc space-y-0.5 pl-5 text-xs">
                    {result.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}

              <Block title="Scores">
                <ul className="grid gap-2 sm:grid-cols-2">
                  {METRIC_NAMES.map((m) => (
                    <li key={m} className="flex items-start justify-between gap-3 rounded-lg border p-2.5">
                      <div>
                        <p className="font-medium">{METRIC_LABELS[m]}</p>
                        <p className="text-muted-foreground mt-0.5 text-[0.7rem] leading-snug">{METRIC_HELP[m]}</p>
                      </div>
                      <ScorePill value={result[m]} />
                    </li>
                  ))}
                </ul>
              </Block>

              <Block title="Answer">
                <p className="whitespace-pre-wrap">{result.answer || "—"}</p>
              </Block>

              {result.ground_truth && (
                <Block title="Expected answer">
                  <p className="whitespace-pre-wrap">{result.ground_truth}</p>
                </Block>
              )}

              {result.unsupported_claims.length > 0 && (
                <Block title="Claims the sources do not support">
                  <ul className="list-disc space-y-1 pl-5">
                    {result.unsupported_claims.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </Block>
              )}

              <Block title={`Retrieved context (${result.contexts.length})`}>
                {result.contexts.length === 0 ? (
                  <p className="text-muted-foreground">Nothing was retrieved.</p>
                ) : (
                  <ol className="space-y-2">
                    {result.contexts.map((c, i) => (
                      <li key={i} className="bg-muted/40 rounded-lg border p-2.5 text-xs leading-relaxed">
                        <span className="text-muted-foreground mr-1 font-semibold">[{i + 1}]</span>
                        {c}
                      </li>
                    ))}
                  </ol>
                )}
              </Block>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
