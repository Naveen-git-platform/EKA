import type { AgentEvent, Source } from "@/lib/api/schemas"

export const source = (index: number, over: Partial<Source> = {}): Source => ({
  index,
  chunk_id: `doc:${index}`,
  doc_id: "doc",
  filename: `policy-${index}.md`,
  page: null,
  section: "Leave",
  score: 0.9 - index * 0.1,
  snippet: `Snippet ${index}`,
  text: `Full-time employees receive 20 days of PTO per year. Unused days roll over up to 5 days. Source ${index}.`,
  ...over,
})

export const plan: AgentEvent = {
  type: "plan",
  strategy: "multi_query",
  standalone_query: "How many PTO days?",
  sub_queries: ["How many PTO days?", "PTO policy"],
  reasoning: "Two phrasings",
  fallback: false,
}

export const retrieval = (n = 1, total = 4): AgentEvent => ({
  type: "retrieval",
  iteration: n,
  queries: ["How many PTO days?"],
  total,
  chunks: [
    {
      chunk_id: "doc:1",
      filename: "policy-1.md",
      page: null,
      section: "Leave",
      score: 0.8,
      sources: ["vector", "bm25"],
      snippet: "s",
    },
  ],
})

export const critique = (over: Partial<Extract<AgentEvent, { type: "critique" }>> = {}): AgentEvent => ({
  type: "critique",
  iteration: 1,
  sufficient: true,
  confidence: 0.9,
  relevance: 0.9,
  coverage: 0.8,
  missing_information: "",
  rewritten_queries: [],
  will_retry: false,
  reasoning: "Enough evidence",
  degraded: false,
  ...over,
})

export const done = (over: Partial<Extract<AgentEvent, { type: "done" }>> = {}): AgentEvent => ({
  type: "done",
  ok: true,
  answer: "Employees receive 20 days of PTO [1].",
  iterations: 1,
  elapsed_ms: 1234,
  trace: [
    { node: "planner", ms: 200, ok: true },
    { node: "retriever", ms: 50, ok: true },
    { node: "critic", ms: 300, ok: true },
    { node: "answer", ms: 600, ok: true },
  ],
  errors: [],
  grounded: true,
  ...over,
})

export const happyPath = (): AgentEvent[] => [
  plan,
  retrieval(),
  critique(),
  { type: "token", text: "Employees receive " },
  { type: "token", text: "20 days of PTO [1]." },
  { type: "citations", citations: [source(1)], sources: [source(1), source(2)] },
  done(),
]

/** Encode events as an SSE body, like the backend does. */
export const sseBody = (events: AgentEvent[]): string =>
  events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join("")
