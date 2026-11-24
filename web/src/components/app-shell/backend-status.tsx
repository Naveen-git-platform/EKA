"use client"

import { useHealth } from "@/lib/api/health"
import { cn } from "@/lib/utils"

/** Coloured dot + label showing whether the backend is reachable and which model it will use. */
export function BackendStatus({ className }: { className?: string }) {
  const { data, isPending, isError } = useHealth()
  const state = isPending ? "checking" : isError ? "offline" : "online"
  const label =
    state === "checking"
      ? "Checking backend"
      : state === "offline"
        ? "Backend offline"
        : `${data?.llm_provider} / ${data?.llm_model}`
  return (
    <div
      role="status"
      aria-live="polite"
      data-state={state}
      className={cn("text-muted-foreground flex min-w-0 items-center gap-2 text-xs", className)}
    >
      <span
        aria-hidden
        className={cn(
          "size-2 shrink-0 rounded-full",
          state === "online" && "bg-success shadow-[0_0_8px_var(--success)]",
          state === "offline" && "bg-destructive",
          state === "checking" && "bg-warning animate-pulse",
        )}
      />
      <span className="truncate">{label}</span>
    </div>
  )
}
