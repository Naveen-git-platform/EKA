"use client"

import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import { ScorePill } from "@/components/evaluation/score-pill"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { RunInfo } from "@/lib/api/schemas"
import { formatDateTime } from "@/lib/format"
import { cn } from "@/lib/utils"

type Props = {
  runs: RunInfo[]
  selectedId: string | null
  onSelect: (runId: string | null) => void
}

function StatusBadge({ status }: { status: RunInfo["status"] }) {
  if (status === "running")
    return (
      <Badge variant="secondary" className="gap-1">
        <Loader2 className="size-3 animate-spin" aria-hidden /> Running
      </Badge>
    )
  if (status === "failed")
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="size-3" aria-hidden /> Failed
      </Badge>
    )
  return (
    <Badge variant="outline" className="gap-1">
      <CheckCircle2 className="text-success size-3" aria-hidden /> Completed
    </Badge>
  )
}

export function RunsTable({ runs, selectedId, onSelect }: Props) {
  if (runs.length === 0) return <p className="text-muted-foreground text-sm">No evaluation runs yet.</p>
  return (
    <div className="overflow-hidden rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="hidden sm:table-cell">Progress</TableHead>
            <TableHead>Overall</TableHead>
            <TableHead className="hidden md:table-cell">Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => {
            const selected = run.run_id === selectedId
            const pct = run.total ? Math.round((run.completed / run.total) * 100) : 0
            return (
              <TableRow
                key={run.run_id}
                data-state={selected ? "selected" : undefined}
                className={cn(selected && "bg-accent/40")}
              >
                <TableCell>
                  <button
                    type="button"
                    onClick={() => onSelect(selected ? null : run.run_id)}
                    aria-pressed={selected}
                    className="hover:text-primary text-left font-medium underline-offset-2 hover:underline"
                  >
                    {run.name || run.run_id}
                  </button>
                  <p className="text-muted-foreground text-xs">{run.backend}</p>
                </TableCell>
                <TableCell>
                  <StatusBadge status={run.status} />
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <div className="flex items-center gap-2">
                    <Progress value={pct} className="w-24" aria-label={`${run.name || run.run_id} progress`} />
                    <span className="text-muted-foreground text-xs tabular-nums">
                      {run.completed}/{run.total}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <ScorePill value={run.aggregate.overall} />
                </TableCell>
                <TableCell className="text-muted-foreground hidden md:table-cell">
                  {formatDateTime(run.created_at)}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
