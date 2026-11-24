import { ReactFlowProvider } from "@xyflow/react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentNode } from "@/components/chat/trace-graph"
import { TracePanel } from "@/components/chat/trace-panel"
import type { AgentEvent } from "@/lib/api/schemas"
import { applyEvent, emptyRun } from "@/lib/chat/run"
import type { TraceNodeData } from "@/lib/chat/trace-graph"
import { critique, done, happyPath, plan, retrieval } from "@/test/fixtures"

vi.mock("next/dynamic", async () => {
  const React = await import("react")
  return { default: () => () => React.createElement("div", { "data-testid": "trace-graph" }) }
})

const fold = (events: AgentEvent[]) => events.reduce(applyEvent, emptyRun())

const nodeData = (over: Partial<TraceNodeData> = {}): TraceNodeData => ({
  id: "critic",
  title: "Critic",
  detail: "sufficient · 90%",
  status: "done",
  warn: false,
  ms: 300,
  ...over,
})

function renderNode(data: TraceNodeData) {
  // The node only reads `data`; the remaining NodeProps are irrelevant to rendering.
  const props = { id: data.id, data } as unknown as Parameters<typeof AgentNode>[0]
  return render(
    <ReactFlowProvider>
      <AgentNode {...props} />
    </ReactFlowProvider>,
  )
}

describe("AgentNode", () => {
  it("shows title, detail and timing with its status", () => {
    const { container } = renderNode(nodeData())
    expect(screen.getByText("Critic")).toBeInTheDocument()
    expect(screen.getByText("sufficient · 90%")).toBeInTheDocument()
    expect(screen.getByText("300 ms")).toBeInTheDocument()
    expect(container.querySelector("[data-status]")).toHaveAttribute("data-status", "done")
  })

  it("shows a degraded marker instead of the timing", () => {
    renderNode(nodeData({ warn: true }))
    expect(screen.getByLabelText("Degraded")).toBeInTheDocument()
    expect(screen.queryByText("300 ms")).not.toBeInTheDocument()
  })

  it("renders every status", () => {
    for (const status of ["idle", "active", "done", "error"] as const) {
      const { container, unmount } = renderNode(nodeData({ status, ms: null }))
      expect(container.querySelector("[data-status]")).toHaveAttribute("data-status", status)
      unmount()
    }
  })
})

describe("TracePanel", () => {
  it("renders the graph and a section per agent step", () => {
    render(<TracePanel run={fold(happyPath())} streaming={false} />)
    expect(screen.getByTestId("trace-graph")).toBeInTheDocument()
    expect(screen.getByText("Plan")).toBeInTheDocument()
    expect(screen.getByText("multi query")).toBeInTheDocument()
    expect(screen.getByText("Retrieval pass 1 · 4 chunks")).toBeInTheDocument()
    expect(screen.getByText("vector")).toBeInTheDocument()
    expect(screen.getByText("bm25")).toBeInTheDocument()
    expect(screen.getByText("Critic review 1")).toBeInTheDocument()
    expect(screen.getByText("Sufficient")).toBeInTheDocument()
    expect(screen.getByText(/confidence 90%/)).toBeInTheDocument()
    expect(screen.getByText("Timing")).toBeInTheDocument()
  })

  it("shows the re-search queries when the critic sent the agent back", () => {
    const run = fold([
      plan,
      retrieval(1),
      critique({ sufficient: false, will_retry: true, rewritten_queries: ["PTO accrual rules"] }),
    ])
    render(<TracePanel run={run} streaming />)
    expect(screen.getByText("Insufficient")).toBeInTheDocument()
    expect(screen.getByText("PTO accrual rules")).toBeInTheDocument()
  })

  it("lists problems the agents reported", () => {
    const run = fold([
      plan,
      { type: "error", stage: "critic", message: "model timeout" },
      done({ ok: false, answer: "" }),
    ])
    render(<TracePanel run={run} streaming={false} />)
    expect(screen.getByText("Problems")).toBeInTheDocument()
    expect(screen.getByText(/model timeout/)).toBeInTheDocument()
  })

  it("marks fallback plans and an unavailable critic", () => {
    const fallbackPlan = { ...plan, fallback: true } as AgentEvent
    render(<TracePanel run={fold([fallbackPlan, retrieval(), critique({ degraded: true })])} streaming={false} />)
    expect(screen.getByText("fallback plan")).toBeInTheDocument()
    expect(screen.getByText("critic unavailable")).toBeInTheDocument()
  })

  it("copes with a run that has just started", () => {
    render(<TracePanel run={emptyRun()} streaming />)
    expect(screen.getByTestId("trace-graph")).toBeInTheDocument()
    expect(screen.queryByText("Plan")).not.toBeInTheDocument()
  })
})
