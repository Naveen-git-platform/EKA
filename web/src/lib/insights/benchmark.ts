import type { Benchmark } from "@/lib/api/schemas"

export type BenchmarkMetric = "recall" | "mrr" | "hit_rate"

export const METRIC_TITLES: Record<BenchmarkMetric, string> = {
  recall: "Recall",
  mrr: "MRR (rank of the first right chunk)",
  hit_rate: "Hit rate",
}

/** Tidy a method label from the benchmark file: drop the "[default]" marker. */
export const methodLabel = (raw: string) => raw.replace(/\s*\[default\]\s*$/i, "").trim()

export const isDefaultMethod = (raw: string) => /\[default\]/i.test(raw)

export type BenchmarkRow = { category: string } & Record<string, number | string | null>

/** Category order shown in the chart; unknown categories follow alphabetically. */
const CATEGORY_ORDER = ["all", "standard", "paraphrase", "keyword"]

export function categories(b: Benchmark): string[] {
  const found = new Set<string>()
  for (const cats of Object.values(b.results)) for (const c of Object.keys(cats)) found.add(c)
  return [...found].sort((x, y) => {
    const ix = CATEGORY_ORDER.indexOf(x)
    const iy = CATEGORY_ORDER.indexOf(y)
    return (ix === -1 ? 99 : ix) - (iy === -1 ? 99 : iy) || x.localeCompare(y)
  })
}

export function methods(b: Benchmark): string[] {
  return Object.keys(b.results)
}

/** One row per question category, one numeric column per retrieval method, for a grouped bar chart. */
export function benchmarkRows(b: Benchmark, metric: BenchmarkMetric): BenchmarkRow[] {
  const key = `${metric}@${b.k}`
  return categories(b).map((category) => {
    const row: BenchmarkRow = { category }
    for (const [method, cats] of Object.entries(b.results)) row[methodLabel(method)] = cats[category]?.[key] ?? null
    return row
  })
}

/** The method with the highest overall score for a metric, ties broken by listing order. */
export function bestMethod(b: Benchmark, metric: BenchmarkMetric): { method: string; value: number } | null {
  const key = `${metric}@${b.k}`
  let best: { method: string; value: number } | null = null
  for (const [method, cats] of Object.entries(b.results)) {
    const v = cats.all?.[key]
    if (typeof v === "number" && (best === null || v > best.value + 1e-12))
      best = { method: methodLabel(method), value: v }
  }
  return best
}
