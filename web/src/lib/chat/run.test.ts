import { describe, expect, it } from "vitest"

import type { AgentEvent } from "@/lib/api/schemas"
import { applyEvent, emptyRun, isRunning, stageLabel } from "@/lib/chat/run"
import { critique, done, happyPath, plan, retrieval, source } from "@/test/fixtures"

const fold = (events: AgentEvent[]) => events.reduce(applyEvent, emptyRun())

describe("applyEvent", () => {
  it("starts in the planning stage with nothing recorded", () => {
    expect(emptyRun()).toMatchObject({ stage: "planning", plan: null, retrievals: [], critiques: [], done: null })
  })

  it("moves through the stages in order", () => {
    expect(fold([plan]).stage).toBe("retrieving")
    expect(fold([plan, retrieval()]).stage).toBe("critiquing")
    expect(fold([plan, retrieval(), critique()]).stage).toBe("answering")
  })

  it("goes back to retrieving when the critic asks for another pass", () => {
    const run = fold([plan, retrieval(1), critique({ sufficient: false, will_retry: true, rewritten_queries: ["q2"] })])
    expect(run.stage).toBe("retrieving")
    const again = applyEvent(run, retrieval(2, 6))
    expect(again.retrievals).toHaveLength(2)
    expect(again.stage).toBe("critiquing")
  })

  it("records citations and sources", () => {
    const run = applyEvent(emptyRun(), { type: "citations", citations: [source(1)], sources: [source(1), source(2)] })
    expect(run.citations).toHaveLength(1)
    expect(run.sources).toHaveLength(2)
  })

  it("finishes as done or error depending on the done event", () => {
    expect(fold(happyPath()).stage).toBe("done")
    expect(fold([plan, done({ ok: false, answer: "" })]).stage).toBe("error")
  })

  it("keeps non-fatal errors without ending the run", () => {
    const run = fold([plan, { type: "error", stage: "critic", message: "boom" }])
    expect(run.errors).toEqual([{ stage: "critic", message: "boom" }])
    expect(run.stage).toBe("retrieving")
  })

  it("does not mutate the previous trace", () => {
    const before = emptyRun()
    applyEvent(before, plan)
    expect(before.plan).toBeNull()
  })

  it("a token moves to answering and is otherwise a no-op", () => {
    const run = fold([plan])
    const next = applyEvent(run, { type: "token", text: "x" })
    expect(next.stage).toBe("answering")
    expect(applyEvent(next, { type: "token", text: "y" })).toBe(next)
  })
})

describe("helpers", () => {
  it("labels every stage", () => {
    for (const s of ["planning", "retrieving", "critiquing", "answering", "done", "error"] as const)
      expect(stageLabel(s)).toBeTruthy()
  })

  it("isRunning is true only before the run ends", () => {
    expect(isRunning(undefined)).toBe(false)
    expect(isRunning(emptyRun())).toBe(true)
    expect(isRunning(fold(happyPath()))).toBe(false)
  })
})
