import { formatMs } from "@/lib/format"
import type { RunTrace } from "@/lib/chat/types"

export type NodeId = "planner" | "retriever" | "critic" | "answer"
export type NodeStatus = "idle" | "active" | "done" | "error"

export type TraceNodeData = {
  id: NodeId
  title: string
  detail: string
  status: NodeStatus
  /** Something degraded (fallback plan, critic unavailable) but the run carried on. */
  warn: boolean
  ms: number | null
}

export type TraceNode = { id: NodeId; type: "agent"; position: { x: number; y: number }; data: TraceNodeData }
export type TraceEdge = {
  id: string
  source: NodeId
  target: NodeId
  sourceHandle?: string
  targetHandle?: string
  type?: "smoothstep"
  label?: string
  animated: boolean
}

export const NODE_ORDER: NodeId[] = ["planner", "retriever", "critic", "answer"]
const TITLES: Record<NodeId, string> = {
  planner: "Planner",
  retriever: "Retriever",
  critic: "Critic",
  answer: "Answer",
}
const ACTIVE_BY_STAGE = {
  planning: "planner",
  retrieving: "retriever",
  critiquing: "critic",
  answering: "answer",
} as const

const plural = (n: number, word: string, many = `${word}s`) => `${n} ${n === 1 ? word : many}`

/** Turn a run trace into React Flow nodes/edges. Pure, so the layout and statuses can be unit-tested. */
export function buildTraceGraph(
  run: RunTrace | undefined,
  streaming: boolean,
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  const active =
    streaming && run && run.stage in ACTIVE_BY_STAGE ? ACTIVE_BY_STAGE[run.stage as keyof typeof ACTIVE_BY_STAGE] : null
  const ms = (id: NodeId) => {
    const steps = run?.done?.trace.filter((t) => t.node === id) ?? []
    return steps.length ? steps.reduce((sum, t) => sum + t.ms, 0) : null
  }
  const lastRetrieval = run?.retrievals.at(-1)
  const lastCritique = run?.critiques.at(-1)
  const answerFailed = !!run && run.stage === "error"

  const details: Record<NodeId, { detail: string; complete: boolean; warn: boolean }> = {
    planner: {
      detail: run?.plan
        ? `${run.plan.strategy.replace("_", " ")} · ${plural(run.plan.sub_queries.length, "query", "queries")}`
        : "Waiting",
      complete: !!run?.plan,
      warn: !!run?.plan?.fallback,
    },
    retriever: {
      detail: lastRetrieval
        ? `${plural(lastRetrieval.total, "chunk")} · ${run!.retrievals.length} ${run!.retrievals.length === 1 ? "pass" : "passes"}`
        : "Waiting",
      complete: !!lastRetrieval,
      warn: false,
    },
    critic: {
      detail: lastCritique
        ? `${lastCritique.sufficient ? "sufficient" : "insufficient"} · ${Math.round(lastCritique.confidence * 100)}%`
        : "Waiting",
      complete: !!lastCritique,
      warn: !!lastCritique?.degraded,
    },
    answer: {
      detail: run?.done
        ? `${plural(run.citations.length, "citation")} · ${formatMs(run.done.elapsed_ms)}`
        : active === "answer"
          ? "Writing…"
          : "Waiting",
      complete: !!run?.done,
      warn: false,
    },
  }

  const nodes: TraceNode[] = NODE_ORDER.map((id, i) => {
    const d = details[id]
    let status: NodeStatus = "idle"
    if (active === id) status = "active"
    else if (id === "answer" && answerFailed) status = "error"
    else if (d.complete) status = "done"
    return {
      id,
      type: "agent",
      position: { x: i * 210, y: 0 },
      data: { id, title: TITLES[id], detail: d.detail, status, warn: d.warn, ms: ms(id) },
    }
  })

  const flowActive = (to: NodeId) => active === to
  const edges: TraceEdge[] = [
    { id: "planner-retriever", source: "planner", target: "retriever", animated: flowActive("retriever") },
    { id: "retriever-critic", source: "retriever", target: "critic", animated: flowActive("critic") },
    { id: "critic-answer", source: "critic", target: "answer", animated: flowActive("answer") },
  ]
  const retries = Math.max(0, (run?.retrievals.length ?? 0) - 1)
  if (retries > 0) {
    edges.push({
      id: "critic-retriever-loop",
      source: "critic",
      target: "retriever",
      sourceHandle: "loop-out",
      targetHandle: "loop-in",
      type: "smoothstep",
      label: `re-retrieved ×${retries}`,
      animated: active === "retriever",
    })
  }
  return { nodes, edges }
}
