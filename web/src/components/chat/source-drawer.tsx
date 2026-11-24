"use client"

import { ChevronLeft, ChevronRight, FileText } from "lucide-react"
import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import type { Source } from "@/lib/api/schemas"
import { claimForCitation } from "@/lib/chat/citations"
import { highlightBestSentences } from "@/lib/chat/highlight"

type Props = {
  sources: Source[]
  /** Source numbers the answer actually cites. */
  cited: number[]
  answer: string
  openIndex: number | null
  onOpenIndexChange: (index: number | null) => void
}

export function SourceDrawer({ sources, cited, answer, openIndex, onOpenIndexChange }: Props) {
  const position = sources.findIndex((s) => s.index === openIndex)
  const source = position >= 0 ? sources[position] : null

  const claim = useMemo(() => (source ? claimForCitation(answer, source.index) : ""), [answer, source])
  const segments = useMemo(() => (source ? highlightBestSentences(source.text, claim) : []), [source, claim])
  const highlighted = segments.some((s) => s.hit)

  const go = (delta: number) => {
    const next = sources[position + delta]
    if (next) onOpenIndexChange(next.index)
  }

  return (
    <Sheet open={source !== null} onOpenChange={(open) => !open && onOpenIndexChange(null)}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-lg">
        {source && (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="flex items-center gap-2">
                <FileText className="text-muted-foreground size-4 shrink-0" aria-hidden />
                <span className="truncate">{source.filename ?? "Document"}</span>
              </SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary">Source {source.index}</Badge>
                {source.page ? <Badge variant="outline">Page {source.page}</Badge> : null}
                {source.section ? <Badge variant="outline">{source.section}</Badge> : null}
                <Badge variant={cited.includes(source.index) ? "default" : "outline"}>
                  {cited.includes(source.index) ? "Cited in answer" : "Retrieved, not cited"}
                </Badge>
                <span className="text-xs">relevance {source.score.toFixed(2)}</span>
              </SheetDescription>
            </SheetHeader>

            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {claim && (
                <div className="bg-muted/50 rounded-lg border p-3">
                  <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">The answer says</p>
                  <p className="text-sm">{claim}</p>
                </div>
              )}
              <div>
                <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">
                  Source text {highlighted ? "· best match highlighted" : ""}
                </p>
                <p className="text-sm leading-relaxed whitespace-pre-wrap" data-testid="source-text">
                  {segments.map((s, i) =>
                    s.hit ? (
                      <mark key={i} className="bg-primary/25 text-foreground rounded px-0.5">
                        {s.text}
                      </mark>
                    ) : (
                      <span key={i}>{s.text}</span>
                    ),
                  )}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between border-t p-3">
              <Button variant="ghost" size="sm" onClick={() => go(-1)} disabled={position <= 0}>
                <ChevronLeft /> Previous
              </Button>
              <span className="text-muted-foreground text-xs">
                {position + 1} of {sources.length}
              </span>
              <Button variant="ghost" size="sm" onClick={() => go(1)} disabled={position >= sources.length - 1}>
                Next <ChevronRight />
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
