import { METRIC_NAMES, type Aggregate, type EvaluationResult, type MetricName } from "@/lib/api/schemas"

export const METRIC_LABELS: Record<MetricName, string> = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer relevancy",
  context_precision: "Context precision",
  context_recall: "Context recall",
}

export const METRIC_HELP: Record<MetricName, string> = {
  faithfulness: "Share of the answer's claims that the retrieved text actually supports. Low means hallucination.",
  answer_relevancy: "How directly the answer addresses the question, regardless of whether it is correct.",
  context_precision: "Share of the retrieved chunks that were useful for the answer. Low means noisy retrieval.",
  context_recall: "Share of the reference answer that the retrieved chunks cover. Needs a ground-truth answer.",
}

export type Tone = "good" | "ok" | "bad" | "none"

/** Colour band for a 0-1 score. Thresholds are deliberately simple and shown to the user in the legend. */
export function scoreTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined || Number.isNaN(value)) return "none"
  if (value >= 0.85) return "good"
  if (value >= 0.6) return "ok"
  return "bad"
}

export const TONE_CLASS: Record<Tone, string> = {
  good: "bg-success/15 text-success",
  ok: "bg-warning/15 text-warning",
  bad: "bg-destructive/15 text-destructive",
  none: "bg-muted text-muted-foreground",
}

export type RadarPoint = { metric: MetricName; label: string; value: number; missing: boolean }

export function radarData(aggregate: Aggregate | undefined): RadarPoint[] {
  return METRIC_NAMES.map((metric) => {
    const v = aggregate?.[metric]
    return { metric, label: METRIC_LABELS[metric], value: v ?? 0, missing: v === null || v === undefined }
  })
}

export type TimelinePoint = { n: number; at: string; overall: number; rolling: number; question: string }

/** Overall score per scored result, oldest first, with a trailing mean to show the trend through the noise. */
export function timeline(results: EvaluationResult[], window = 5): TimelinePoint[] {
  const scored = results
    .filter((r) => typeof r.overall === "number")
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
  return scored.map((r, i) => {
    const slice = scored.slice(Math.max(0, i - window + 1), i + 1)
    const rolling = slice.reduce((sum, x) => sum + (x.overall as number), 0) / slice.length
    return { n: i + 1, at: r.created_at, overall: r.overall as number, rolling, question: r.question }
  })
}

export type CategoryStat = { category: string; overall: number; count: number }

export function byCategory(results: EvaluationResult[]): CategoryStat[] {
  const groups = new Map<string, number[]>()
  for (const r of results) {
    if (typeof r.overall !== "number") continue
    const key = r.category || "uncategorised"
    groups.set(key, [...(groups.get(key) ?? []), r.overall])
  }
  return [...groups]
    .map(([category, vals]) => ({
      category,
      overall: vals.reduce((a, b) => a + b, 0) / vals.length,
      count: vals.length,
    }))
    .sort((a, b) => a.category.localeCompare(b.category))
}

export type ResultHealth = "ok" | "partial" | "failed"

/** `failed`: the pipeline errored and nothing could be scored. `partial`: something was missing or errored. */
export function resultHealth(r: EvaluationResult): ResultHealth {
  const scored = METRIC_NAMES.filter((m) => typeof r[m] === "number").length
  if (r.errors.length > 0 && scored === 0) return "failed"
  // Missing context_recall is normal without a ground truth, so it alone does not make a result partial.
  const expected = r.ground_truth ? METRIC_NAMES.length : METRIC_NAMES.length - 1
  if (r.errors.length > 0 || scored < expected) return "partial"
  return "ok"
}

export function countByHealth(results: EvaluationResult[]): Record<ResultHealth, number> {
  const out: Record<ResultHealth, number> = { ok: 0, partial: 0, failed: 0 }
  for (const r of results) out[resultHealth(r)]++
  return out
}

export type ParsedCases = {
  cases: { question: string; ground_truth: string | null }[]
  /** 1-based line numbers that were skipped, with the reason. */
  problems: { line: number; reason: string }[]
}

export const MAX_CUSTOM_CASES = 100

/** One case per line: `question`, or `question || expected answer`. Blank lines are ignored. */
export function parseCases(text: string): ParsedCases {
  const cases: ParsedCases["cases"] = []
  const problems: ParsedCases["problems"] = []
  const seen = new Set<string>()
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim()
    if (!line) return
    const [q, ...rest] = line.split("||")
    const question = q.trim()
    const truth = rest.join("||").trim()
    if (!question) return void problems.push({ line: i + 1, reason: "Missing question" })
    if (question.length > 2000)
      return void problems.push({ line: i + 1, reason: "Question is longer than 2000 characters" })
    if (truth.length > 4000)
      return void problems.push({ line: i + 1, reason: "Expected answer is longer than 4000 characters" })
    const key = question.toLowerCase()
    if (seen.has(key)) return void problems.push({ line: i + 1, reason: "Duplicate question" })
    seen.add(key)
    if (cases.length >= MAX_CUSTOM_CASES)
      return void problems.push({ line: i + 1, reason: `Only ${MAX_CUSTOM_CASES} cases per run` })
    cases.push({ question, ground_truth: truth || null })
  })
  return { cases, problems }
}
