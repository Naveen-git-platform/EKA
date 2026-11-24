"use client"

import { useQuery } from "@tanstack/react-query"

import { request } from "@/lib/api/client"
import { MapResponseSchema, StatsSchema, type MapResponse, type Stats } from "@/lib/api/schemas"
import { useSettings } from "@/lib/store/settings"

export const MAP_POINT_LIMIT = 2500

export const fetchStats = (): Promise<Stats> => request("/insights/stats", StatsSchema)

export function fetchMap(maxPoints = MAP_POINT_LIMIT): Promise<MapResponse> {
  return request(`/insights/map?max_points=${maxPoints}`, MapResponseSchema)
}

export function useStats() {
  const apiUrl = useSettings((s) => s.apiUrl)
  return useQuery({ queryKey: ["stats", apiUrl], queryFn: fetchStats })
}

export function useKnowledgeMap() {
  const apiUrl = useSettings((s) => s.apiUrl)
  // The projection only changes when documents change, and those mutations invalidate the "map" key.
  return useQuery({ queryKey: ["map", apiUrl], queryFn: () => fetchMap(), staleTime: 60_000 })
}
