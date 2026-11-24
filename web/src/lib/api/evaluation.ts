"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { request } from "@/lib/api/client"
import {
  EvaluationListSchema,
  RunInfoSchema,
  RunListSchema,
  type BatchEvaluateRequest,
  type EvaluationList,
  type RunInfo,
} from "@/lib/api/schemas"
import { useSettings } from "@/lib/store/settings"

export const RESULTS_LIMIT = 500

export const fetchRuns = () => request("/evaluations/runs?limit=50", RunListSchema)

export function fetchEvaluations(runId: string | null, limit = RESULTS_LIMIT): Promise<EvaluationList> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (runId) params.set("run_id", runId)
  return request(`/evaluations?${params}`, EvaluationListSchema)
}

export const startBatch = (body: BatchEvaluateRequest): Promise<RunInfo> =>
  request("/evaluate/batch", RunInfoSchema, { method: "POST", json: body })

export const isRunning = (runs: RunInfo[] | undefined, runId: string | null): boolean =>
  !!runs?.some((r) => r.status === "running" && (runId === null || r.run_id === runId))

/** Runs list; polls every 2s while any batch is still running so progress bars move. */
export function useRuns() {
  const apiUrl = useSettings((s) => s.apiUrl)
  return useQuery({
    queryKey: ["runs", apiUrl],
    queryFn: fetchRuns,
    refetchInterval: (q) => (isRunning(q.state.data?.runs, null) ? 2000 : false),
  })
}

/** Results for one run (or all). Re-fetches while that run is in progress so new rows appear as they finish. */
export function useEvaluations(runId: string | null, running: boolean) {
  const apiUrl = useSettings((s) => s.apiUrl)
  return useQuery({
    queryKey: ["evaluations", apiUrl, runId],
    queryFn: () => fetchEvaluations(runId),
    refetchInterval: running ? 2500 : false,
  })
}

export function useStartBatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: startBatch,
    onSuccess: () => {
      for (const key of ["runs", "evaluations", "stats"]) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}
