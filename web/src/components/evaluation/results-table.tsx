"use client"

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table"
import { AlertTriangle, ArrowDown, ArrowUp, ChevronLeft, ChevronRight, XCircle } from "lucide-react"
import { useMemo, useState } from "react"

import { ScorePill } from "@/components/evaluation/score-pill"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { EvaluationResult } from "@/lib/api/schemas"
import { METRIC_LABELS, resultHealth } from "@/lib/eval/metrics"
import { formatMs } from "@/lib/format"

const col = createColumnHelper<EvaluationResult>()
const PAGE_SIZE = 10

type Props = {
  results: EvaluationResult[]
  onOpen: (result: EvaluationResult) => void
}

/** Missing values (null) must sort last whichever way the column is sorted. */
const nullsLast = (a: number | null | undefined, b: number | null | undefined, desc: boolean) => {
  const an = typeof a === "number"
  const bn = typeof b === "number"
  if (an && bn) return (a as number) - (b as number)
  if (!an && !bn) return 0
  return (an ? -1 : 1) * (desc ? -1 : 1)
}

export function ResultsTable({ results, onOpen }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }])

  const columns = useMemo(
    () => [
      col.accessor("question", {
        header: "Question",
        cell: (c) => {
          const r = c.row.original
          const health = resultHealth(r)
          return (
            <button type="button" onClick={() => onOpen(r)} className="group flex max-w-md items-start gap-2 text-left">
              {health === "failed" ? (
                <XCircle className="text-destructive mt-0.5 size-4 shrink-0" aria-label="Failed" />
              ) : health === "partial" ? (
                <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-label="Partly scored" />
              ) : null}
              <span className="group-hover:text-primary line-clamp-2 underline-offset-2 group-hover:underline">
                {r.question}
              </span>
            </button>
          )
        },
      }),
      ...(["faithfulness", "answer_relevancy", "context_precision", "context_recall"] as const).map((m) =>
        col.accessor((r) => r[m] ?? null, {
          id: m,
          header: METRIC_LABELS[m],
          cell: (c) => <ScorePill value={c.getValue()} />,
          sortingFn: (a, b, id) =>
            nullsLast(
              a.getValue<number | null>(id),
              b.getValue<number | null>(id),
              sorting.find((s) => s.id === id)?.desc ?? false,
            ),
          sortUndefined: "last",
        }),
      ),
      col.accessor((r) => r.overall ?? null, {
        id: "overall",
        header: "Overall",
        cell: (c) => <ScorePill value={c.getValue()} className="font-semibold" />,
        sortingFn: (a, b, id) =>
          nullsLast(
            a.getValue<number | null>(id),
            b.getValue<number | null>(id),
            sorting.find((s) => s.id === id)?.desc ?? false,
          ),
        sortUndefined: "last",
      }),
      col.accessor((r) => r.latency_ms ?? null, {
        id: "latency_ms",
        header: "Time",
        cell: (c) => <span className="text-muted-foreground tabular-nums">{formatMs(c.getValue())}</span>,
        sortingFn: (a, b, id) =>
          nullsLast(
            a.getValue<number | null>(id),
            b.getValue<number | null>(id),
            sorting.find((s) => s.id === id)?.desc ?? false,
          ),
        sortUndefined: "last",
      }),
      col.accessor("created_at", { header: "When", cell: () => null, enableHiding: true }),
    ],
    [onOpen, sorting],
  )

  // TanStack Table returns non-memoizable functions; nothing here relies on React Compiler memoization.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: results,
    columns,
    state: { sorting, columnVisibility: { created_at: false } },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: PAGE_SIZE } },
    autoResetPageIndex: true,
  })

  const { pageIndex } = table.getState().pagination
  const pages = table.getPageCount()

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => {
                  const sorted = h.column.getIsSorted()
                  return (
                    <TableHead key={h.id} aria-sort={sorted ? (sorted === "asc" ? "ascending" : "descending") : "none"}>
                      <button
                        type="button"
                        onClick={h.column.getToggleSortingHandler()}
                        className="hover:text-foreground inline-flex items-center gap-1 whitespace-nowrap"
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {sorted === "asc" && <ArrowUp className="size-3" aria-hidden />}
                        {sorted === "desc" && <ArrowDown className="size-3" aria-hidden />}
                      </button>
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length - 1} className="text-muted-foreground h-24 text-center">
                  No results to show.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {pageIndex + 1} of {pages} · {results.length} results
          </span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Previous page"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <ChevronLeft />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Next page"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
