import { describe, expect, it } from "vitest"

import type { AgentEvent } from "@/lib/api/schemas"
import { applyEvent, emptyRun } from "@/lib/chat/run"
import { buildTraceGraph, NODE_ORDER } from "@/lib/chat/trace-graph"
import { critique, done, happyPath, plan, retrieval, source } from "@/test/fixtures"

const fold = (events: AgentEvent[]) => events.reduce(applyEvent, emptyRun())
const status = (g: ReturnType<typeof buildTraceGraph>) => Object.fromEntries(g.nodes.map((n) => [n.id, n.data.status]))

describe("buildTraceGraph", () => {
  it("always lays out the four agents left to right in pipeline order", () => {
    const g = buildTraceGraph(undefined, false)
    expect(g.nodes.map((n) => n.id)).toEqual(NODE_ORDER)
    const xs = g.nodes.map((n) => n.position.x)
    expect([...xs].sort((a, b) => a - b)).toEqual(xs)
    expect(g.edges.map((e) => e.id)).toEqual(["planner-retriever", "retriever-critic", "critic-answer"])
  })

  it("is idle before a run exists", () => {
    expect(status(buildTraceGraph(undefined, false))).toEqual({
      planner: "idle",
      retriever: "idle",
      critic: "idle",
      answer: "idle",
    })
  })

  it("highlights the agent that is working while streaming", () => {
    expect(status(buildTraceGraph(emptyRun(), true)).planner).toBe("active")
    const mid = buildTraceGraph(fold([plan]), true)
    expect(status(mid)).toMatchObject({ planner: "done", retriever: "active", critic: "idle" })
    const writing = buildTraceGraph(fold([plan, retrieval(), critique(), { type: "token", text: "x" }]), true)
    expect(status(writing)).toMatchObject({ critic: "done", answer: "active" })
    expect(writing.nodes[3].data.detail).toBe("Writing…")
  })

  it("marks everything done with details and timings after a successful run", () => {
    const g = buildTraceGraph(fold(happyPath()), false)
    expect(Object.values(status(g))).toEqual(["done", "done", "done", "done"])
    expect(g.nodes[0].data.detail).toBe("multi query · 2 queries")
    expect(g.nodes[1].data.detail).toBe("4 chunks · 1 pass")
    expect(g.nodes[2].data.detail).toBe("sufficient · 90%")
    expect(g.nodes[3].data.detail).toBe("1 citation · 1.2 s")
    expect(g.nodes.map((n) => n.data.ms)).toEqual([200, 50, 300, 600])
  })

  it("adds an animated-aware loop edge when the critic sent it back", () => {
    const run = fold([plan, retrieval(1), critique({ sufficient: false, will_retry: true }), retrieval(2, 7)])
    const g = buildTraceGraph(run, true)
    const loop = g.edges.find((e) => e.id === "critic-retriever-loop")
    expect(loop).toMatchObject({
      source: "critic",
      target: "retriever",
      label: "re-retrieved ×1",
      sourceHandle: "loop-out",
      targetHandle: "loop-in",
    })
    expect(g.nodes[1].data.detail).toBe("7 chunks · 2 passes")
  })

  it("sums the time of repeated passes of the same agent", () => {
    const run = fold([
      plan,
      retrieval(1),
      retrieval(2),
      done({
        trace: [
          { node: "retriever", ms: 40, ok: true },
          { node: "retriever", ms: 60, ok: true },
        ],
      }),
    ])
    expect(buildTraceGraph(run, false).nodes[1].data.ms).toBe(100)
  })

  it("flags degraded planner / critic without failing the run", () => {
    const fallbackPlan = { ...plan, fallback: true } as AgentEvent
    const g = buildTraceGraph(fold([fallbackPlan, retrieval(), critique({ degraded: true })]), false)
    expect(g.nodes[0].data.warn).toBe(true)
    expect(g.nodes[2].data.warn).toBe(true)
    expect(g.nodes[0].data.status).toBe("done")
  })

  it("marks the answer node as failed when the run ended in error", () => {
    const g = buildTraceGraph(fold([plan, retrieval(), critique(), done({ ok: false, answer: "" })]), false)
    expect(status(g).answer).toBe("error")
  })

  it("pluralises citations", () => {
    const run = fold([
      plan,
      retrieval(),
      critique(),
      { type: "citations", citations: [source(1), source(2)], sources: [] },
      done(),
    ])
    expect(buildTraceGraph(run, false).nodes[3].data.detail).toContain("2 citations")
  })

  it("is not active when not streaming even if the stage is mid-run (stopped message)", () => {
    expect(status(buildTraceGraph(fold([plan]), false)).retriever).toBe("idle")
  })
})
