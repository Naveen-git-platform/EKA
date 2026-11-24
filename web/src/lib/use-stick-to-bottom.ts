"use client"

import { useCallback, useEffect, useRef } from "react"

/**
 * Keep a scroll container pinned to the bottom while content streams in, but stop following as soon as the
 * reader scrolls up (within `threshold` px of the bottom counts as "at the bottom").
 */
export function useStickToBottom<T extends HTMLElement>(trigger: unknown, threshold = 120) {
  const ref = useRef<T>(null)
  const stick = useRef(true)

  const onScroll = useCallback(() => {
    const el = ref.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }, [threshold])

  const scrollToBottom = useCallback(() => {
    stick.current = true
    const el = ref.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  useEffect(() => {
    const el = ref.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [trigger])

  return { ref, onScroll, scrollToBottom }
}
