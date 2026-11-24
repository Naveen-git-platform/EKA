import { describe, expect, it } from "vitest"

import {
  AgentEventSchema,
  DocumentListSchema,
  EvaluationListSchema,
  HealthSchema,
  MapResponseSchema,
  RunInfoSchema,
  StatsSchema,
  UploadResponseSchema,
} from "@/lib/api/schemas"
import { healthFixture } from "@/test/server"

describe("backend payload schemas", () => {
  it("parses /health", () => {
    expect(HealthSchema.parse(healthFixture).llm_model).toBe("openai/gpt-oss-120b")
    expect(HealthSchema.parse({ ...healthFixture, documents: null }).documents).toBeNull()
  })

  it("parses every agent event type", () => {
    const events = [
      { type: "plan", strategy: "multi_query", standalone_query: "q", sub_queries: ["a", "b"] },
      {
        type: "retrieval",
        iteration: 1,
        queries: ["q"],
        total: 1,
        chunks: [{ chunk_id: "c", score: 0.4, snippet: "s", sources: ["vector"] }],
      },
      {
        type: "critique",
        iteration: 1,
        sufficient: true,
        confidence: 0.9,
        relevance: 0.8,
        coverage: 0.7,
        will_retry: false,
      },
      { type: "token", text: "x" },
      { type: "citations", citations: [], sources: [] },
      { type: "error", stage: "answer", message: "boom" },
      { type: "done", ok: true, answer: "a", iterations: 1, elapsed_ms: 5, grounded: false },
    ]
    for (const ev of events) expect(AgentEventSchema.safeParse(ev).success, ev.type).toBe(true)
  })

  it("applies defaults for optional agent-event fields", () => {
    const plan = AgentEventSchema.parse({ type: "plan", strategy: "direct", standalone_query: "q", sub_queries: [] })
    expect(plan).toMatchObject({ reasoning: "", fallback: false })
  })

  it("rejects unknown event types and bad strategies", () => {
    expect(AgentEventSchema.safeParse({ type: "nope" }).success).toBe(false)
    expect(
      AgentEventSchema.safeParse({ type: "plan", strategy: "weird", standalone_query: "q", sub_queries: [] }).success,
    ).toBe(false)
  })

  it("parses documents and uploads", () => {
    const doc = {
      doc_id: "d1",
      filename: "a.pdf",
      file_type: "pdf",
      size_bytes: 10,
      chunk_count: 2,
      page_count: 3,
      created_at: "now",
    }
    expect(DocumentListSchema.parse({ documents: [doc], total: 1, total_chunks: 2 }).documents).toHaveLength(1)
    const up = UploadResponseSchema.parse({
      results: [
        { filename: "a.pdf", status: "indexed" },
        { filename: "b", status: "failed", error: "x" },
      ],
    })
    expect(up.indexed).toBe(0)
    expect(UploadResponseSchema.safeParse({ results: [{ filename: "a", status: "weird" }] }).success).toBe(false)
  })

  it("parses evaluation results with null metrics", () => {
    const r = { id: "1", created_at: "t", question: "q", answer: "a", faithfulness: null, overall: 0.5 }
    const parsed = EvaluationListSchema.parse({
      results: [r],
      total: 1,
      aggregate: { faithfulness: null, overall: 0.5, count: 1 },
    })
    expect(parsed.results[0].contexts).toEqual([])
    expect(parsed.results[0].source).toBe("api")
  })

  it("parses runs, stats and the knowledge map", () => {
    expect(
      RunInfoSchema.parse({ run_id: "r", created_at: "t", status: "running", total: 3, completed: 1 }).aggregate,
    ).toEqual({})
    const stats = StatsSchema.parse({
      documents: 1,
      chunks: 2,
      file_types: { pdf: 1 },
      llm_provider: "groq",
      llm_model: "m",
      embedding_provider: "e",
      embedding_model: "em",
      evaluation: { count: 0, runs: 0, aggregate: {} },
      benchmark: null,
    })
    expect(stats.benchmark).toBeNull()
    const map = MapResponseSchema.parse({
      points: [{ chunk_id: "c", doc_id: "d", filename: "f", snippet: "s", x: 0, y: 0.5, z: -1 }],
      documents: [{ doc_id: "d", filename: "f", chunks: 1 }],
      total: 1,
      truncated: false,
      explained_variance: [0.5, 0.2, 0.1],
    })
    expect(map.points[0].page).toBeUndefined()
  })
})
