import { formatScore } from "@/lib/format"
import { scoreTone, TONE_CLASS } from "@/lib/eval/metrics"
import { cn } from "@/lib/utils"

/** A 0-1 score as a small coloured pill. A missing score shows a dash, never a misleading 0. */
export function ScorePill({ value, className }: { value: number | null | undefined; className?: string }) {
  const tone = scoreTone(value)
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-block min-w-10 rounded-md px-1.5 py-0.5 text-center text-xs font-medium tabular-nums",
        TONE_CLASS[tone],
        className,
      )}
    >
      {formatScore(value)}
    </span>
  )
}
