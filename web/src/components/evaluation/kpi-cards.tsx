import { Card, CardContent } from "@/components/ui/card"
import { METRIC_NAMES, type Aggregate } from "@/lib/api/schemas"
import { METRIC_HELP, METRIC_LABELS, scoreTone, TONE_CLASS } from "@/lib/eval/metrics"
import { formatMs, formatNumber, formatPercent } from "@/lib/format"
import { cn } from "@/lib/utils"

type Props = {
  aggregate: Aggregate | undefined
  count: number
  avgLatencyMs: number | null
}

function Kpi({
  label,
  value,
  tone,
  hint,
  big,
}: {
  label: string
  value: string
  tone?: ReturnType<typeof scoreTone>
  hint?: string
  big?: boolean
}) {
  return (
    <Card size="sm" className={cn(big && "bg-accent/30")}>
      <CardContent className="space-y-1">
        <p className="text-muted-foreground text-xs font-medium">{label}</p>
        <p
          className={cn(
            "font-semibold tabular-nums",
            big ? "text-3xl" : "text-xl",
            tone && tone !== "none" && TONE_CLASS[tone].split(" ")[1],
          )}
        >
          {value}
        </p>
        {hint && <p className="text-muted-foreground line-clamp-2 text-[0.7rem] leading-snug">{hint}</p>}
      </CardContent>
    </Card>
  )
}

export function KpiCards({ aggregate, count, avgLatencyMs }: Props) {
  const overall = aggregate?.overall
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6" aria-label="Key metrics" role="group">
      <div className="sm:col-span-2 lg:col-span-1">
        <Kpi
          label="Overall score"
          value={formatPercent(overall)}
          tone={scoreTone(overall)}
          hint={`${formatNumber(count)} answers scored`}
          big
        />
      </div>
      {METRIC_NAMES.map((m) => (
        <Kpi
          key={m}
          label={METRIC_LABELS[m]}
          value={formatPercent(aggregate?.[m])}
          tone={scoreTone(aggregate?.[m])}
          hint={METRIC_HELP[m]}
        />
      ))}
      <Kpi
        label="Avg. response time"
        value={formatMs(avgLatencyMs)}
        hint="Planning, retrieval, review and answer together."
      />
    </div>
  )
}
