"use client"

import { useQuery } from "@tanstack/react-query"

import { request } from "@/lib/api/client"
import { HealthSchema, type Health } from "@/lib/api/schemas"
import { useSettings } from "@/lib/store/settings"

export const fetchHealth = (): Promise<Health> => request("/health", HealthSchema)

/** Backend liveness + active model configuration. Re-checked every 15s so the status dot stays honest. */
export function useHealth() {
  const apiUrl = useSettings((s) => s.apiUrl)
  return useQuery({
    queryKey: ["health", apiUrl],
    queryFn: fetchHealth,
    refetchInterval: 15_000,
    retry: false,
  })
}
