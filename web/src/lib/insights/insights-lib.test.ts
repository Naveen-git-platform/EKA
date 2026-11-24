import { describe, expect, it } from "vitest"

import type { MapPoint } from "@/lib/api/schemas"
import { applyEvent, emptyRun } from "@/lib/chat/run"
import type { Message } from "@/lib/chat/types"
import { benchmarkRows, bestMethod, categories, isDefaultMethod, methodLabel, methods } from "@/lib/insights/benchmark"
import {
  answerOptions,
  buildPointBuffers,
  colorForDocs,
  DOC_PALETTE,
  fibonacciSphere,
  retrievedIds,
  SCENE_RADIUS,
  webglAvailable,
} from "@/lib/insights/map"
import { critique, done, plan, retrieval, source } from "@/test/fixtures"

const benchmark = {
  k: 3,
  results: {
    "vector only": {
      all: { "recall@3": 0.9, "mrr@3": 0.8 },
      keyword: { "recall@3": 1 },
      paraphrase: { "recall@3": 0.8 },
    },
    "BM25 only": {
      all: { "recall@3": 0.7, "mrr@3": 0.6 },
      keyword: { "recall@3": 1 },
      paraphrase: { "recall@3": 0.4 },
    },
    "hybrid (weighted 0.7) [default]": {
      all: { "recall@3": 0.95, "mrr@3": 0.9 },
      keyword: { "recall@3": 1 },
      paraphrase: { "recall@3": 0.9 },
    },
  },
}

describe("benchmark helpers", () => {
  it("cleans method labels and detects the default", () => {
    expect(methodLabel("hybrid (weighted 0.7) [default]")).toBe("hybrid (weighted 0.7)")
    expect(isDefaultMethod("hybrid (weighted 0.7) [default]")).toBe(true)
    expect(isDefaultMethod("vector only")).toBe(false)
  })

  it("orders categories with 'all' first and unknown ones last", () => {
    const b = { ...benchmark, results: { m: { zeta: {}, keyword: {}, all: {}, standard: {}, paraphrase: {} } } }
    expect(categories(b)).toEqual(["all", "standard", "paraphrase", "keyword", "zeta"])
  })

  it("lists methods in file order", () => {
    expect(methods(benchmark)).toEqual(["vector only", "BM25 only", "hybrid (weighted 0.7) [default]"])
  })

  it("builds one row per category with a column per method, null when absent", () => {
    const rows = benchmarkRows(benchmark, "recall")
    expect(rows.map((r) => r.category)).toEqual(["all", "paraphrase", "keyword"])
    expect(rows[0]).toMatchObject({ "vector only": 0.9, "BM25 only": 0.7, "hybrid (weighted 0.7)": 0.95 })
    const mrr = benchmarkRows(benchmark, "mrr")
    expect(mrr.find((r) => r.category === "keyword")?.["vector only"]).toBeNull()
  })

  it("finds the best method overall", () => {
    expect(bestMethod(benchmark, "recall")).toEqual({ method: "hybrid (weighted 0.7)", value: 0.95 })
    expect(bestMethod(benchmark, "hit_rate")).toBeNull()
  })
})

const pt = (id: string, doc: string, x: number, y: number, z: number): MapPoint => ({
  chunk_id: id,
  doc_id: doc,
  filename: `${doc}.md`,
  snippet: id,
  x,
  y,
  z,
  page: null,
  section: null,
})
const points = [pt("a", "d1", 1, 0, 0), pt("b", "d1", 0, 1, 0), pt("c", "d2", 0, 0, -1)]

describe("colorForDocs", () => {
  it("assigns palette colours in order and wraps around", () => {
    const docs = Array.from({ length: DOC_PALETTE.length + 1 }, (_, i) => ({ doc_id: `d${i}` }))
    const colors = colorForDocs(docs)
    expect(colors.get("d0")).toBe(DOC_PALETTE[0])
    expect(colors.get(`d${DOC_PALETTE.length}`)).toBe(DOC_PALETTE[0])
  })
})

describe("buildPointBuffers", () => {
  const colors = colorForDocs([{ doc_id: "d1" }, { doc_id: "d2" }])

  it("scales coordinates into the scene and keeps a source index", () => {
    const b = buildPointBuffers(points, { colors })
    expect(b.count).toBe(3)
    expect(b.positions[0]).toBeCloseTo(SCENE_RADIUS, 5)
    expect(b.positions[1]).toBe(0)
    expect(b.positions[2]).toBe(0)
    expect(b.sourceIndex).toEqual([0, 1, 2])
    expect(b.colors).toHaveLength(9)
  })

  it("leaves out hidden documents and maps slots back to the original indexes", () => {
    const b = buildPointBuffers(points, { colors, hiddenDocs: new Set(["d1"]) })
    expect(b.count).toBe(1)
    expect(b.sourceIndex).toEqual([2])
  })

  it("can include only, or exclude, a set of chunks", () => {
    expect(buildPointBuffers(points, { colors, only: new Set(["b"]) }).sourceIndex).toEqual([1])
    expect(buildPointBuffers(points, { colors, exclude: new Set(["b"]) }).sourceIndex).toEqual([0, 2])
  })

  it("applies a colour override and the document colour otherwise", () => {
    const own = buildPointBuffers(points, { colors })
    expect(own.colors[0]).toBeCloseTo(0x8b / 255, 4) // first palette colour, red channel
    const white = buildPointBuffers(points, { colors, color: "#ffffff" })
    expect(Array.from(white.colors.slice(0, 3))).toEqual([1, 1, 1])
  })

  it("falls back to the first palette colour for an unknown document and handles empty input", () => {
    expect(buildPointBuffers([pt("z", "unknown", 0, 0, 0)], { colors }).count).toBe(1)
    expect(buildPointBuffers([], { colors }).count).toBe(0)
  })
})

const botMessage = (events: Parameters<typeof applyEvent>[1][]): Message => ({
  id: "m",
  role: "assistant",
  content: "x",
  status: "done",
  createdAt: 0,
  run: events.reduce(applyEvent, emptyRun()),
})

describe("retrievedIds / answerOptions", () => {
  it("collects every retrieved chunk and the cited ones", () => {
    const m = botMessage([
      plan,
      retrieval(1),
      critique(),
      retrieval(2),
      {
        type: "citations",
        citations: [source(1, { chunk_id: "doc:1" })],
        sources: [source(1, { chunk_id: "doc:1" }), source(2, { chunk_id: "doc:2" })],
      },
      done(),
    ])
    const ids = retrievedIds(m)
    expect([...ids.retrieved].sort()).toEqual(["doc:1", "doc:2"])
    expect([...ids.cited]).toEqual(["doc:1"])
  })

  it("is empty without a run", () => {
    expect(retrievedIds(undefined).retrieved.size).toBe(0)
    expect(retrievedIds({ id: "u", role: "user", content: "hi", status: "done", createdAt: 0 }).cited.size).toBe(0)
  })

  it("lists recent answers newest first, labelled by their question, skipping ones without retrieval", () => {
    const user = (id: string, content: string): Message => ({ id, role: "user", content, status: "done", createdAt: 0 })
    const withRetrieval = (id: string) => ({ ...botMessage([plan, retrieval(1)]), id })
    const messages = [
      user("u1", "First question"),
      withRetrieval("a1"),
      user("u2", "Second   question"),
      { ...botMessage([plan]), id: "a2" },
      user("u3", "Third question"),
      withRetrieval("a3"),
    ]
    const opts = answerOptions(messages, "Chat title")
    expect(opts.map((o) => o.id)).toEqual(["a3", "a1"])
    expect(opts.map((o) => o.label)).toEqual(["Third question", "First question"])
  })

  it("truncates long labels and respects the limit", () => {
    const long = "q".repeat(100)
    const messages: Message[] = [
      { id: "u", role: "user", content: long, status: "done", createdAt: 0 },
      botMessage([plan, retrieval(1)]),
    ]
    expect(answerOptions(messages, "t")[0].label).toHaveLength(70)
    const many: Message[] = Array.from({ length: 20 }, (_, i) => ({ ...botMessage([plan, retrieval(1)]), id: `a${i}` }))
    expect(answerOptions(many, "t", 3)).toHaveLength(3)
  })
})

describe("fibonacciSphere", () => {
  it("places every point on the sphere surface", () => {
    const pts = fibonacciSphere(200, 3)
    expect(pts).toHaveLength(600)
    for (let i = 0; i < 200; i++) {
      const r = Math.hypot(pts[i * 3], pts[i * 3 + 1], pts[i * 3 + 2])
      expect(r).toBeCloseTo(3, 4)
    }
  })

  it("covers both poles and is not clumped on one side", () => {
    const pts = fibonacciSphere(500, 1)
    let up = 0
    for (let i = 0; i < 500; i++) if (pts[i * 3 + 1] > 0) up++
    expect(up).toBeGreaterThan(230)
    expect(up).toBeLessThan(270)
  })

  it("handles one point and zero points", () => {
    expect(fibonacciSphere(1, 2)).toHaveLength(3)
    expect(fibonacciSphere(0, 2)).toHaveLength(0)
  })
})

describe("webglAvailable", () => {
  it("is false where no GL context can be created (jsdom)", () => {
    expect(webglAvailable()).toBe(false)
  })
})
