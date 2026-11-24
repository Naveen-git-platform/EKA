import { describe, expect, it } from "vitest"

import {
  byCategory,
  countByHealth,
  MAX_CUSTOM_CASES,
  parseCases,
  radarData,
  resultHealth,
  scoreTone,
  timeline,
} from "@/lib/eval/metrics"
import { failedResult, result } from "@/test/eval-fixtures"

describe("scoreTone", () => {
  it.each([
    [1, "good"],
    [0.85, "good"],
    [0.849, "ok"],
    [0.6, "ok"],
    [0.599, "bad"],
    [0, "bad"],
    [null, "none"],
    [undefined, "none"],
    [Number.NaN, "none"],
  ])("%s -> %s", (v, tone) => expect(scoreTone(v as number | null | undefined)).toBe(tone))
})

describe("radarData", () => {
  it("lists the four metrics in order and marks missing values without inventing a zero score", () => {
    const d = radarData({ faithfulness: 0.9, answer_relevancy: null, context_precision: 0.5 })
    expect(d.map((p) => p.metric)).toEqual(["faithfulness", "answer_relevancy", "context_precision", "context_recall"])
    expect(d.map((p) => p.missing)).toEqual([false, true, false, true])
    expect(d[0].value).toBe(0.9)
    expect(d.map((p) => p.short)).toEqual(["Faithfulness", "Relevancy", "Precision", "Recall"])
    expect(d.every((p) => p.short.length <= 12)).toBe(true) // must fit beside a radar axis
  })

  it("handles no data at all", () => {
    expect(radarData(undefined).every((p) => p.missing)).toBe(true)
  })
})

describe("timeline", () => {
  it("orders by time, skips unscored results and computes a trailing mean", () => {
    const rs = [
      result({ id: "b", created_at: "2026-01-01T00:00:02Z", overall: 0.5 }),
      result({ id: "a", created_at: "2026-01-01T00:00:01Z", overall: 1 }),
      failedResult({ id: "x", created_at: "2026-01-01T00:00:03Z" }),
      result({ id: "c", created_at: "2026-01-01T00:00:04Z", overall: 0 }),
    ]
    const t = timeline(rs, 2)
    expect(t.map((p) => p.overall)).toEqual([1, 0.5, 0])
    expect(t.map((p) => p.rolling)).toEqual([1, 0.75, 0.25])
    expect(t.map((p) => p.n)).toEqual([1, 2, 3])
  })

  it("is empty when nothing is scored", () => {
    expect(timeline([failedResult()])).toEqual([])
    expect(timeline([])).toEqual([])
  })

  it("does not mutate its input", () => {
    const rs = [result({ created_at: "2026-01-01T00:00:09Z" }), result({ created_at: "2026-01-01T00:00:01Z" })]
    const before = rs.map((r) => r.id)
    timeline(rs)
    expect(rs.map((r) => r.id)).toEqual(before)
  })
})

describe("byCategory", () => {
  it("averages overall per category and sorts alphabetically", () => {
    const stats = byCategory([
      result({ category: "paraphrase", overall: 0.8 }),
      result({ category: "keyword", overall: 1 }),
      result({ category: "paraphrase", overall: 0.6 }),
      result({ category: null, overall: 0.5 }),
      failedResult({ category: "keyword" }),
    ])
    expect(stats.map((s) => s.category)).toEqual(["keyword", "paraphrase", "uncategorised"])
    expect(stats.find((s) => s.category === "paraphrase")).toMatchObject({ count: 2 })
    expect(stats.find((s) => s.category === "paraphrase")?.overall).toBeCloseTo(0.7)
    expect(stats.find((s) => s.category === "keyword")?.count).toBe(1)
  })
})

describe("resultHealth", () => {
  it("is ok when everything was scored", () => {
    expect(resultHealth(result())).toBe("ok")
  })

  it("does not penalise a missing context recall when there is no ground truth", () => {
    expect(resultHealth(result({ ground_truth: null, context_recall: null }))).toBe("ok")
  })

  it("is partial when a metric is missing despite a ground truth, or when errors were reported", () => {
    expect(resultHealth(result({ context_recall: null }))).toBe("partial")
    expect(resultHealth(result({ errors: ["context_precision: HTTP 429"] }))).toBe("partial")
  })

  it("is failed when the pipeline errored and nothing was scored", () => {
    expect(resultHealth(failedResult())).toBe("failed")
  })

  it("counts each kind", () => {
    expect(countByHealth([result(), result(), failedResult(), result({ context_recall: null })])).toEqual({
      ok: 2,
      partial: 1,
      failed: 1,
    })
  })
})

describe("parseCases", () => {
  it("parses questions with optional expected answers", () => {
    const { cases, problems } = parseCases("How many days?  ||  20 days\nWho approves?\n\n  Third one || ")
    expect(cases).toEqual([
      { question: "How many days?", ground_truth: "20 days" },
      { question: "Who approves?", ground_truth: null },
      { question: "Third one", ground_truth: null },
    ])
    expect(problems).toEqual([])
  })

  it("keeps extra separators inside the expected answer", () => {
    expect(parseCases("q || a || b").cases[0]).toEqual({ question: "q", ground_truth: "a || b" })
  })

  it("reports bad lines with their 1-based number", () => {
    const { cases, problems } = parseCases("ok question\n || only an answer\nOK QUESTION\n" + "x".repeat(2001))
    expect(cases).toHaveLength(1)
    expect(problems).toEqual([
      { line: 2, reason: "Missing question" },
      { line: 3, reason: "Duplicate question" },
      { line: 4, reason: "Question is longer than 2000 characters" },
    ])
  })

  it("caps the number of cases", () => {
    const text = Array.from({ length: MAX_CUSTOM_CASES + 3 }, (_, i) => `question ${i}`).join("\n")
    const { cases, problems } = parseCases(text)
    expect(cases).toHaveLength(MAX_CUSTOM_CASES)
    expect(problems).toHaveLength(3)
  })

  it("handles Windows line endings and empty input", () => {
    expect(parseCases("a\r\nb").cases).toHaveLength(2)
    expect(parseCases("").cases).toEqual([])
    expect(parseCases("  \n \n").problems).toEqual([])
  })
})
