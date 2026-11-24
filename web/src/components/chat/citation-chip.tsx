"use client"

import type { Source } from "@/lib/api/schemas"
import { cn } from "@/lib/utils"

type Props = {
  n: number
  source?: Source
  onOpen?: (n: number) => void
}

/** A small clickable `[n]` in the answer. Without a matching source (still streaming, or a bogus number) it is inert. */
export function CitationChip({ n, source, onOpen }: Props) {
  const interactive = !!source && !!onOpen
  return (
    <button
      type="button"
      disabled={!interactive}
      onClick={() => onOpen?.(n)}
      aria-label={source ? `Source ${n}: ${source.filename ?? "document"}` : `Source ${n}`}
      title={source ? (source.filename ?? undefined) : undefined}
      className={cn(
        "mx-0.5 inline-flex h-[1.35em] min-w-[1.35em] items-center justify-center rounded-md px-1 align-baseline text-[0.72em] leading-none font-semibold tabular-nums transition-colors",
        interactive
          ? "bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground cursor-pointer"
          : "bg-muted text-muted-foreground cursor-default",
      )}
    >
      {n}
    </button>
  )
}
