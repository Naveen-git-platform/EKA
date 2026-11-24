import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { BenchmarkChart } from "@/components/insights/benchmark-chart"
import { InsightsView } from "@/components/insights/insights-view"
import { KnowledgeMap } from "@/components/insights/knowledge-map"
import { HeroBackground } from "@/components/three/hero-background"
import type { AgentEvent, MapResponse, Stats } from "@/lib/api/schemas"
import { applyEvent, emptyRun } from "@/lib/chat/run"
import type { Message } from "@/lib/chat/types"
import { pointSize } from "@/lib/insights/map"
import { DEFAULT_CHAT_SETTINGS, useChat } from "@/lib/store/chat"
import { critique, done, plan, source } from "@/test/fixtures"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

// jsdom has no WebGL, so the map renders its 2D fallback; the 3D canvas itself is covered by the pure-logic tests.
vi.mock("next/dynamic", async () => {
  const React = await import("react")
  return { default: () => () => React.createElement("div", { "data-testid": "three-canvas" }) }
})

const benchmark = {
  embedder: "all-MiniLM-L6-v2",
  k: 3,
  n_documents: 4,
  n_questions: 36,
  results: {
    "vector only": {
      all: { "recall@3": 0.9861, "mrr@3": 0.95, "hit_rate@3": 1 },
      keyword: { "recall@3": 1, "mrr@3": 1, "hit_rate@3": 1 },
    },
    "hybrid (weighted 0.7) [default]": {
      all: { "recall@3": 1, "mrr@3": 0.97, "hit_rate@3": 1 },
      keyword: { "recall@3": 1, "mrr@3": 1, "hit_rate@3": 1 },
    },
  },
}

const stats: Stats = {
  documents: 4,
  chunks: 17,
  file_types: { md: 1, pdf: 1 },
  llm_provider: "groq",
  llm_model: "openai/gpt-oss-120b",
  embedding_provider: "sentence-transformers",
  embedding_model: "sentence-transformers/all-MiniLM-L6-v2",
  evaluation: { count: 6, runs: 1, aggregate: { overall: 0.9618 }, avg_latency_ms: 3100 },
  benchmark,
}

const map: MapResponse = {
  points: [
    {
      chunk_id: "a:0",
      doc_id: "a",
      filename: "handbook.md",
      section: "Leave",
      page: null,
      snippet: "PTO is 20 days",
      x: 0.5,
      y: 0.2,
      z: 0,
    },
    {
      chunk_id: "a:1",
      doc_id: "a",
      filename: "handbook.md",
      section: "Expenses",
      page: null,
      snippet: "Expenses within 30 days",
      x: -0.4,
      y: 0.1,
      z: 0.3,
    },
    {
      chunk_id: "b:0",
      doc_id: "b",
      filename: "runbook.pdf",
      section: null,
      page: 2,
      snippet: "Page the on-call engineer",
      x: 0,
      y: -0.6,
      z: -0.2,
    },
  ],
  documents: [
    { doc_id: "a", filename: "handbook.md", chunks: 2 },
    { doc_id: "b", filename: "runbook.pdf", chunks: 1 },
  ],
  total: 3,
  truncated: false,
  explained_variance: [0.4, 0.2, 0.1],
}

const answer = (): Message => {
  const events: AgentEvent[] = [
    plan,
    {
      type: "retrieval",
      iteration: 1,
      queries: ["q"],
      total: 1,
      chunks: [{ chunk_id: "a:0", filename: "handbook.md", score: 0.9, sources: ["vector"], snippet: "x" }],
    },
    critique(),
    {
      type: "citations",
      citations: [source(1, { chunk_id: "a:0" })],
      sources: [source(1, { chunk_id: "a:0" }), source(2, { chunk_id: "b:0" })],
    },
    done(),
  ]
  return {
    id: "ans",
    role: "assistant",
    content: "PTO is 20 days [1].",
    status: "done",
    createdAt: 2,
    run: events.reduce(applyEvent, emptyRun()),
  }
}

beforeEach(() => {
  useChat.setState({ conversations: [], activeId: null, settings: DEFAULT_CHAT_SETTINGS })
  server.use(
    http.get(`${API}/insights/stats`, () => HttpResponse.json(stats)),
    http.get(`${API}/insights/map`, () => HttpResponse.json(map)),
  )
})

describe("pointSize", () => {
  it("shrinks as the number of points grows", () => {
    const sizes = [10, 200, 1000, 3000].map(pointSize)
    expect([...sizes].sort((a, b) => b - a)).toEqual(sizes)
    expect(new Set(sizes).size).toBe(4)
  })
})

describe("BenchmarkChart", () => {
  it("names the best method and which one the app uses", () => {
    render(<BenchmarkChart benchmark={benchmark} />)
    expect(screen.getByText(/Best overall for recall/)).toHaveTextContent("hybrid (weighted 0.7)")
    expect(screen.getByText(/The app uses/)).toHaveTextContent("hybrid (weighted 0.7)")
  })

  it("exposes the numbers as a table and switches metric", async () => {
    const user = userEvent.setup()
    render(<BenchmarkChart benchmark={benchmark} />)
    const table = screen.getByRole("table")
    expect(table).toHaveTextContent("Recall by question category and retrieval method")
    expect(within(table).getByText("98.6%")).toBeInTheDocument()
    await user.click(screen.getByRole("radio", { name: /MRR/ }))
    expect(screen.getByRole("radio", { name: /MRR/ })).toHaveAttribute("aria-checked", "true")
    expect(screen.getByRole("table")).toHaveTextContent("MRR (rank of the first right chunk) by question category")
    expect(within(screen.getByRole("table")).getByText("97.0%")).toBeInTheDocument()
  })

  it("shows n/a for combinations the benchmark does not contain", () => {
    const sparse = { ...benchmark, results: { m: { all: { "recall@3": 1 }, keyword: {} } } }
    render(<BenchmarkChart benchmark={sparse} />)
    expect(within(screen.getByRole("table")).getByText("n/a")).toBeInTheDocument()
  })
})

describe("InsightsView", () => {
  it("shows statistics, the benchmark and the knowledge map", async () => {
    renderWithProviders(<InsightsView />)
    expect(await screen.findByText("17")).toBeInTheDocument()
    expect(screen.getByText("1 md · 1 pdf")).toBeInTheDocument()
    expect(screen.getByText("all-MiniLM-L6-v2")).toBeInTheDocument()
    expect(screen.getByText(/overall 96%/)).toBeInTheDocument()
    expect(screen.getByText("Retrieval benchmark")).toBeInTheDocument()
    expect(await screen.findByText("Knowledge map")).toBeInTheDocument()
  })

  it("explains how to create a benchmark when none exists", async () => {
    server.use(http.get(`${API}/insights/stats`, () => HttpResponse.json({ ...stats, benchmark: null })))
    renderWithProviders(<InsightsView />)
    expect(await screen.findByText(/No retrieval benchmark found/)).toBeInTheDocument()
  })

  it("reports a failing backend with a retry", async () => {
    server.use(
      http.get(`${API}/insights/stats`, () => HttpResponse.json({ detail: "Service is starting up" }, { status: 503 })),
    )
    renderWithProviders(<InsightsView />)
    expect(await screen.findByText("Service is starting up")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
  })
})

describe("KnowledgeMap (2D fallback when WebGL is unavailable)", () => {
  it("lists the documents and plots every chunk", async () => {
    renderWithProviders(<KnowledgeMap />)
    expect(await screen.findByRole("button", { name: /handbook\.md/ })).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "2D map of document chunks" }).querySelectorAll("circle")).toHaveLength(3)
    expect(screen.getByText(/3 of 3 chunks/)).toBeInTheDocument()
    expect(screen.getByText(/axes explain 40% · 20% · 10%/)).toBeInTheDocument()
    expect(screen.getByText(/this browser cannot show WebGL/)).toBeInTheDocument()
  })

  it("hides and shows a document from the legend", async () => {
    const user = userEvent.setup()
    renderWithProviders(<KnowledgeMap />)
    const legend = await screen.findByRole("button", { name: /handbook\.md/ })
    await user.click(legend)
    expect(legend).toHaveAttribute("aria-pressed", "false")
    expect(screen.getByRole("img", { name: "2D map of document chunks" }).querySelectorAll("circle")).toHaveLength(1)
    await user.click(legend)
    expect(screen.getByRole("img", { name: "2D map of document chunks" }).querySelectorAll("circle")).toHaveLength(3)
  })

  it("pins a clicked chunk and shows where it came from", async () => {
    const user = userEvent.setup()
    renderWithProviders(<KnowledgeMap />)
    await screen.findByRole("button", { name: /handbook\.md/ })
    const circles = screen.getByRole("img", { name: "2D map of document chunks" }).querySelectorAll("circle")
    await user.click(circles[2])
    expect(await screen.findByText("Page the on-call engineer")).toBeInTheDocument()
    expect(screen.getByText(/runbook\.pdf/, { selector: "p" })).toBeInTheDocument()
  })

  it("asks the user to chat first when there is nothing to highlight", async () => {
    renderWithProviders(<KnowledgeMap />)
    await screen.findByRole("button", { name: /handbook\.md/ })
    const select = screen.getByLabelText("Highlight")
    expect(select).toBeDisabled()
    expect(screen.getByRole("option", { name: "Ask a question in Chat first" })).toBeInTheDocument()
  })

  it("highlights the chunks an earlier answer retrieved and cited", async () => {
    const user = userEvent.setup()
    const now = Date.now()
    useChat.setState({
      activeId: "c1",
      conversations: [
        {
          id: "c1",
          title: "PTO",
          createdAt: now,
          updatedAt: now,
          messages: [{ id: "u", role: "user", content: "How many PTO days?", status: "done", createdAt: 1 }, answer()],
        },
      ],
    })
    renderWithProviders(<KnowledgeMap />)
    await screen.findByRole("button", { name: /handbook\.md/ })
    await user.selectOptions(screen.getByLabelText("Highlight"), "ans")
    const badges = await screen.findAllByText(/retrieved|cited/)
    expect(badges.map((b) => b.textContent)).toEqual(expect.arrayContaining(["2 retrieved", "1 cited"]))
    const circles = [...screen.getByRole("img", { name: "2D map of document chunks" }).querySelectorAll("circle")]
    expect(circles.filter((c) => c.getAttribute("fill") === "#ffffff")).toHaveLength(1) // cited
    expect(circles.filter((c) => c.getAttribute("fill") === "#fbbf24")).toHaveLength(1) // retrieved only
  })

  it("says so when no chunks are indexed", async () => {
    server.use(
      http.get(`${API}/insights/map`, () => HttpResponse.json({ ...map, points: [], documents: [], total: 0 })),
    )
    renderWithProviders(<KnowledgeMap />)
    expect(await screen.findByText(/No chunks are indexed yet/)).toBeInTheDocument()
  })

  it("notes when the map shows only a sample of the chunks", async () => {
    server.use(http.get(`${API}/insights/map`, () => HttpResponse.json({ ...map, total: 5000, truncated: true })))
    renderWithProviders(<KnowledgeMap />)
    expect(await screen.findByText(/3 of 5,000 chunks \(sample\)/)).toBeInTheDocument()
  })

  it("reports an error with a retry", async () => {
    server.use(
      http.get(`${API}/insights/map`, () => HttpResponse.json({ detail: "Qdrant unavailable" }, { status: 503 })),
    )
    renderWithProviders(<KnowledgeMap />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Qdrant unavailable")
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument())
  })
})

describe("HeroBackground", () => {
  it("is decorative, hidden from assistive tech and falls back to a CSS glow without WebGL", () => {
    render(<HeroBackground />)
    const bg = screen.getByTestId("hero-background")
    expect(bg).toHaveAttribute("aria-hidden", "true")
    expect(screen.queryByTestId("three-canvas")).not.toBeInTheDocument()
    expect(bg.querySelector("canvas")).toBeNull()
  })
})
