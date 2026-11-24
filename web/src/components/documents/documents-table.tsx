"use client"

import { ArrowDown, ArrowUp, FileText, Search, Trash2 } from "lucide-react"
import { useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { DocumentInfo } from "@/lib/api/schemas"
import { formatBytes, formatDate, formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

type SortKey = "filename" | "size_bytes" | "chunk_count" | "created_at"
type SortDir = "asc" | "desc"

export function sortDocuments(docs: DocumentInfo[], key: SortKey, dir: SortDir): DocumentInfo[] {
  const sign = dir === "asc" ? 1 : -1
  return [...docs].sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    const cmp =
      typeof av === "string"
        ? av.localeCompare(bv as string, undefined, { sensitivity: "base" })
        : (av as number) - (bv as number)
    return cmp * sign || a.filename.localeCompare(b.filename)
  })
}

const COLUMNS: { key: SortKey; label: string; className?: string }[] = [
  { key: "filename", label: "Document" },
  { key: "size_bytes", label: "Size", className: "hidden sm:table-cell" },
  { key: "chunk_count", label: "Chunks" },
  { key: "created_at", label: "Added", className: "hidden md:table-cell" },
]

type Props = {
  documents: DocumentInfo[]
  onDelete: (doc: DocumentInfo) => void
}

export function DocumentsTable({ documents, onDelete }: Props) {
  const [query, setQuery] = useState("")
  const [sortKey, setSortKey] = useState<SortKey>("created_at")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = q ? documents.filter((d) => d.filename.toLowerCase().includes(q)) : documents
    return sortDocuments(filtered, sortKey, sortDir)
  }, [documents, query, sortKey, sortDir])

  const toggle = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    else {
      setSortKey(key)
      setSortDir(key === "filename" ? "asc" : "desc")
    }
  }

  return (
    <div className="space-y-3">
      <div className="relative max-w-xs">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by name…"
          aria-label="Filter documents by name"
          className="pl-8"
        />
      </div>
      <div className="overflow-hidden rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.map(({ key, label, className }) => {
                const active = key === sortKey
                return (
                  <TableHead
                    key={key}
                    className={className}
                    aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <button
                      type="button"
                      onClick={() => toggle(key)}
                      className={cn(
                        "hover:text-foreground inline-flex items-center gap-1",
                        active && "text-foreground",
                      )}
                    >
                      {label}
                      {active &&
                        (sortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden />
                        ))}
                    </button>
                  </TableHead>
                )
              })}
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS.length + 1} className="text-muted-foreground h-24 text-center">
                  No documents match “{query}”.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((doc) => (
                <TableRow key={doc.doc_id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-md">
                        <FileText className="size-4" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-medium">{doc.filename}</p>
                        <p className="text-muted-foreground text-xs">
                          <Badge variant="secondary" className="mr-1.5 uppercase">
                            {doc.file_type}
                          </Badge>
                          {doc.page_count ? `${doc.page_count} pages` : null}
                        </p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">{formatBytes(doc.size_bytes)}</TableCell>
                  <TableCell>{formatNumber(doc.chunk_count)}</TableCell>
                  <TableCell className="hidden md:table-cell">{formatDate(doc.created_at)}</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Delete ${doc.filename}`}
                      onClick={() => onDelete(doc)}
                      className="hover:text-destructive"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
