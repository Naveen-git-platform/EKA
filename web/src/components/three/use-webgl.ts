"use client"

import { useSyncExternalStore } from "react"

import { webglAvailable } from "@/lib/insights/map"

const subscribe = () => () => undefined

/** Whether WebGL works here. `false` on the server and for the first render, so the 2D fallback is the safe default. */
export function useWebgl(): boolean {
  return useSyncExternalStore(subscribe, webglAvailable, () => false)
}
