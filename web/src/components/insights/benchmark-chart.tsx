"use client"

import { useState } from "react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import type { Benchmark } from "@/lib/api/schemas"
import {
  benchmarkRows,
  bestMethod,
  isDefaultMethod,
  methodLabel,
  methods,
  METRIC_TITLES,
  type BenchmarkMetric,
} from "@/lib/insights/benchmark"
import { formatPercent } from "@/lib/format"
import { cn } from "@/lib/utils"

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]
const METRICS: BenchmarkMetric[] = ["recall", "mrr", "hit_rate"]

export function BenchmarkChart({ benchmark }: { benchmark: Benchmark }) {
  const [metric, setMetric] = useState<BenchmarkMetric>("recall")
  const labels = methods(benchmark).map(methodLabel)
  const rows = benchmarkRows(benchmark, metric)
  const best = bestMethod(benchmark, metric)
  const defaultMethod = methods(benchmark).find(isDefaultMethod)

  // Chart keys end up in CSS custom properties (--color-<key>), so they must be plain identifiers; the human-readable
  // method names ("hybrid (weighted 0.7)") only live in the config labels.
  const keys = labels.map((_, i) => `m${i}`)
  const chartRows = rows.map((r) => ({
    category: r.category,
    ...Object.fromEntries(labels.map((l, i) => [keys[i], r[l]])),
  }))
  const config: ChartConfig = Object.fromEntries(
    labels.map((l, i) => [keys[i], { label: l, color: COLORS[i % COLORS.length] }]),
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Retrieval benchmark</CardTitle>
        <CardDescription>
          How often the right chunk is in the top {benchmark.k}, for {benchmark.n_questions ?? "the"} labelled questions
          over {benchmark.n_documents ?? "the"} sample documents. Measured on a small synthetic set, so read it as a
          sanity check, not a verdict.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div role="radiogroup" aria-label="Metric" className="flex flex-wrap gap-1.5">
          {METRICS.map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={metric === m}
              onClick={() => setMetric(m)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                metric === m ? "border-primary bg-accent text-accent-foreground" : "hover:bg-muted",
              )}
            >
              {METRIC_TITLES[m]}
            </button>
          ))}
        </div>

        <ChartContainer config={config} className="h-72 w-full">
          <BarChart data={chartRows} margin={{ left: -16, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="category" tickLine={false} axisLine={false} />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v), 1)} />} />
            <ChartLegend content={<ChartLegendContent />} />
            {keys.map((k) => (
              <Bar key={k} dataKey={k} fill={`var(--color-${k})`} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        </ChartContainer>

        <div className="sr-only">
          <table>
            <caption>{METRIC_TITLES[metric]} by question category and retrieval method</caption>
            <thead>
              <tr>
                <th>Category</th>
                {labels.map((l) => (
                  <th key={l}>{l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.category}>
                  <td>{r.category}</td>
                  {labels.map((l) => (
                    <td key={l}>{typeof r[l] === "number" ? formatPercent(r[l] as number, 1) : "n/a"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {best && (
          <p className="text-muted-foreground text-sm">
            Best overall for {METRIC_TITLES[metric].split(" (")[0].toLowerCase()}:{" "}
            <strong className="text-foreground">{best.method}</strong> ({formatPercent(best.value, 1)}).
            {defaultMethod && (
              <>
                {" "}
                The app uses <strong className="text-foreground">{methodLabel(defaultMethod)}</strong>.
              </>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
