"use client"

import { useSyncExternalStore } from "react"

const subscribe = () => () => undefined

/** `false` during SSR and the first hydration pass, `true` afterwards - avoids theme/localStorage hydration mismatches. */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )
}
