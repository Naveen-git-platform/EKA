import type { EvaluationResult, RunInfo } from "@/lib/api/schemas"

let counter = 0

export const result = (over: Partial<EvaluationResult> = {}): EvaluationResult => {
  counter++
  return {
    id: `e${counter}`,
    run_id: "r1",
    created_at: `2026-11-24T10:${String(counter % 60).padStart(2, "0")}:00+00:00`,
    source: "batch",
    backend: "custom",
    question: `Question ${counter}?`,
    ground_truth: `Truth ${counter}`,
    answer: `Answer ${counter}`,
    contexts: [`Context for ${counter}`],
    faithfulness: 1,
    answer_relevancy: 0.9,
    context_precision: 1,
    context_recall: 1,
    overall: 0.975,
    unsupported_claims: [],
    errors: [],
    latency_ms: 2500,
    case_id: `c${counter}`,
    category: "standard",
    ...over,
  }
}

export const failedResult = (over: Partial<EvaluationResult> = {}) =>
  result({
    faithfulness: null,
    answer_relevancy: null,
    context_precision: null,
    context_recall: null,
    overall: null,
    answer: "",
    contexts: [],
    latency_ms: null,
    errors: ["planner: LLM HTTP 401: Invalid API Key", "answer: LLM HTTP 401: Invalid API Key"],
    ...over,
  })

export const run = (over: Partial<RunInfo> = {}): RunInfo => ({
  run_id: "r1",
  created_at: "2026-11-24T10:00:00+00:00",
  name: "recheck",
  status: "completed",
  total: 6,
  completed: 6,
  backend: "custom",
  aggregate: { faithfulness: 1, answer_relevancy: 0.86, context_precision: 1, context_recall: 1, overall: 0.9618 },
  ...over,
})
