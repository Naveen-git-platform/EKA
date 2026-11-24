import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { CategoryBars, ScoreRadar, ScoreTimeline } from "@/components/evaluation/charts"
import { KpiCards } from "@/components/evaluation/kpi-cards"
import { ResultDetailsSheet } from "@/components/evaluation/result-details-sheet"
import { ResultsTable } from "@/components/evaluation/results-table"
import { RunsTable } from "@/components/evaluation/runs-table"
import { ScorePill } from "@/components/evaluation/score-pill"
import { failedResult, result, run } from "@/test/eval-fixtures"

describe("ScorePill", () => {
  it("shows two decimals with a tone, and a dash for missing scores", () => {
    const { rerender } = render(<ScorePill value={0.9618} />)
    expect(screen.getByText("0.96")).toHaveAttribute("data-tone", "good")
    rerender(<ScorePill value={0.7} />)
    expect(screen.getByText("0.70")).toHaveAttribute("data-tone", "ok")
    rerender(<ScorePill value={0.2} />)
    expect(screen.getByText("0.20")).toHaveAttribute("data-tone", "bad")
    rerender(<ScorePill value={null} />)
    expect(screen.getByText("—")).toHaveAttribute("data-tone", "none")
  })
})

describe("KpiCards", () => {
  it("shows the overall score, each metric and the response time", () => {
    render(
      <KpiCards
        aggregate={{
          faithfulness: 1,
          answer_relevancy: 0.86,
          context_precision: 1,
          context_recall: null,
          overall: 0.9618,
        }}
        count={6}
        avgLatencyMs={3100}
      />,
    )
    const group = screen.getByRole("group", { name: "Key metrics" })
    expect(within(group).getByText("96%")).toBeInTheDocument()
    expect(within(group).getByText("6 answers scored")).toBeInTheDocument()
    expect(within(group).getByText("86%")).toBeInTheDocument()
    expect(within(group).getByText("3.1 s")).toBeInTheDocument()
    // context recall is missing: a dash, not 0%
    expect(within(group).getByText("Context recall").nextSibling).toHaveTextContent("—")
  })

  it("copes with no data", () => {
    render(<KpiCards aggregate={undefined} count={0} avgLatencyMs={null} />)
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(6)
  })
})

describe("charts", () => {
  it("radar exposes its values as text", () => {
    render(
      <ScoreRadar
        aggregate={{ faithfulness: 0.9, answer_relevancy: null, context_precision: 0.5, context_recall: 1 }}
      />,
    )
    const list = screen.getByRole("list", { name: "Quality profile values" })
    expect(list).toHaveTextContent("Faithfulness: 90%")
    expect(list).toHaveTextContent("Answer relevancy: not available")
  })

  it("timeline summarises scored answers and handles the empty case", () => {
    const { rerender } = render(<ScoreTimeline results={[result({ overall: 0.5 }), result({ overall: 0.9 })]} />)
    expect(screen.getByText(/2 scored answers; latest overall/)).toBeInTheDocument()
    rerender(<ScoreTimeline results={[failedResult()]} />)
    expect(screen.getAllByText(/No scored answers yet/).length).toBeGreaterThan(0)
  })

  it("category bars list each category with its count", () => {
    render(
      <CategoryBars
        results={[result({ category: "keyword", overall: 1 }), result({ category: "paraphrase", overall: 0.5 })]}
      />,
    )
    const list = screen.getByRole("list", { name: "Scores by question type" })
    expect(list).toHaveTextContent("keyword: 100% across 1 answers")
    expect(list).toHaveTextContent("paraphrase: 50% across 1 answers")
  })
})

describe("RunsTable", () => {
  it("shows run details and progress", () => {
    render(
      <RunsTable
        runs={[run(), run({ run_id: "r2", name: null, status: "running", total: 10, completed: 4, aggregate: {} })]}
        selectedId={null}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText("recheck")).toBeInTheDocument()
    expect(screen.getByText("Completed")).toBeInTheDocument()
    expect(screen.getByText("Running")).toBeInTheDocument()
    expect(screen.getByText("4/10")).toBeInTheDocument()
    expect(screen.getByText("r2")).toBeInTheDocument() // falls back to the id when unnamed
    expect(screen.getByText("0.96")).toBeInTheDocument()
  })

  it("selects a run, and toggles it off when clicked again", async () => {
    const onSelect = vi.fn()
    const { rerender } = render(<RunsTable runs={[run()]} selectedId={null} onSelect={onSelect} />)
    await userEvent.click(screen.getByRole("button", { name: "recheck" }))
    expect(onSelect).toHaveBeenLastCalledWith("r1")
    rerender(<RunsTable runs={[run()]} selectedId="r1" onSelect={onSelect} />)
    expect(screen.getByRole("button", { name: "recheck" })).toHaveAttribute("aria-pressed", "true")
    await userEvent.click(screen.getByRole("button", { name: "recheck" }))
    expect(onSelect).toHaveBeenLastCalledWith(null)
  })

  it("renders a failed run and an empty list", () => {
    const { rerender } = render(<RunsTable runs={[run({ status: "failed" })]} selectedId={null} onSelect={() => {}} />)
    expect(screen.getByText("Failed")).toBeInTheDocument()
    rerender(<RunsTable runs={[]} selectedId={null} onSelect={() => {}} />)
    expect(screen.getByText("No evaluation runs yet.")).toBeInTheDocument()
  })
})

describe("ResultsTable", () => {
  const rows = [
    result({ id: "a", question: "Alpha question", overall: 0.9, latency_ms: 1000 }),
    result({ id: "b", question: "Bravo question", overall: 0.5, latency_ms: 3000 }),
    failedResult({ id: "c", question: "Charlie question" }),
  ]
  const questions = () =>
    screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[0].textContent)

  it("lists answers with scores and flags the ones that failed", () => {
    render(<ResultsTable results={rows} onOpen={() => {}} />)
    expect(questions()).toHaveLength(3)
    expect(screen.getByLabelText("Failed")).toBeInTheDocument()
  })

  it("sorts by a metric and always puts unscored rows last", async () => {
    const user = userEvent.setup()
    render(<ResultsTable results={rows} onOpen={() => {}} />)
    await user.click(screen.getByRole("button", { name: "Overall" }))
    const first = questions()
    expect(first.at(-1)).toContain("Charlie")
    await user.click(screen.getByRole("button", { name: "Overall" }))
    const second = questions()
    expect(second.at(-1)).toContain("Charlie")
    expect(first[0]).not.toEqual(second[0])
  })

  it("opens the details for a clicked question", async () => {
    const onOpen = vi.fn()
    render(<ResultsTable results={rows} onOpen={onOpen} />)
    await userEvent.click(screen.getByRole("button", { name: /Bravo question/ }))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }))
  })

  it("paginates long lists", async () => {
    const many = Array.from({ length: 23 }, (_, i) => result({ question: `Row ${i}` }))
    const user = userEvent.setup()
    render(<ResultsTable results={many} onOpen={() => {}} />)
    expect(questions()).toHaveLength(10)
    expect(screen.getByText(/Page 1 of 3 · 23 results/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Next page" }))
    expect(questions()).toHaveLength(3)
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled()
  })

  it("has no pager for a short list and a friendly empty state", () => {
    const { rerender } = render(<ResultsTable results={rows} onOpen={() => {}} />)
    expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument()
    rerender(<ResultsTable results={[]} onOpen={() => {}} />)
    expect(screen.getByText("No results to show.")).toBeInTheDocument()
  })
})

describe("ResultDetailsSheet", () => {
  it("stays closed without a result", () => {
    render(<ResultDetailsSheet result={null} onClose={() => {}} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("shows scores, the answer, the expected answer, unsupported claims and context", () => {
    render(
      <ResultDetailsSheet
        result={result({
          question: "How many PTO days?",
          answer: "Twenty days",
          ground_truth: "20 days",
          unsupported_claims: ["Rollover is unlimited"],
          contexts: ["PTO is 20 days", "Other"],
        })}
        onClose={() => {}}
      />,
    )
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent("How many PTO days?")
    expect(dialog).toHaveTextContent("Twenty days")
    expect(dialog).toHaveTextContent("20 days")
    expect(dialog).toHaveTextContent("Rollover is unlimited")
    expect(dialog).toHaveTextContent("Retrieved context (2)")
    expect(within(dialog).getByText("Faithfulness")).toBeInTheDocument()
  })

  it("surfaces pipeline errors prominently (e.g. a bad API key)", () => {
    render(<ResultDetailsSheet result={failedResult({ question: "Broken one" })} onClose={() => {}} />)
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid API Key")
    expect(screen.getByText("Nothing was retrieved.")).toBeInTheDocument()
  })

  it("closes on Escape", async () => {
    const onClose = vi.fn()
    render(<ResultDetailsSheet result={result()} onClose={onClose} />)
    await userEvent.keyboard("{Escape}")
    expect(onClose).toHaveBeenCalled()
  })
})
