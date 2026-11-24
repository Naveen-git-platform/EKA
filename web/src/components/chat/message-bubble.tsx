"use client"

import { AlertCircle, Check, ChevronDown, Copy, Sparkles, Square, User } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { AnswerMarkdown } from "@/components/chat/answer-markdown"
import { TracePanel } from "@/components/chat/trace-panel"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { citedNumbers } from "@/lib/chat/citations"
import { stageLabel } from "@/lib/chat/run"
import type { Message } from "@/lib/chat/types"
import { formatMs } from "@/lib/format"
import { cn } from "@/lib/utils"

type Props = {
  message: Message
  onOpenSource: (messageId: string, index: number) => void
}

function UserBubble({ message }: { message: Message }) {
  return (
    <div className="flex justify-end gap-3">
      <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm whitespace-pre-wrap sm:max-w-[75%]">
        {message.content}
      </div>
      <span className="bg-muted text-muted-foreground hidden size-8 shrink-0 items-center justify-center rounded-full sm:flex">
        <User className="size-4" aria-hidden />
      </span>
    </div>
  )
}

export function MessageBubble({ message, onOpenSource }: Props) {
  const [traceOpen, setTraceOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  if (message.role === "user") return <UserBubble message={message} />

  const streaming = message.status === "streaming"
  const run = message.run
  const sources = run?.sources ?? []
  const cited = citedNumbers(message.content).filter((n) => sources.some((s) => s.index === n))
  const citedSources = sources.filter((s) => cited.includes(s.index))
  const open = (index: number) => onOpenSource(message.id, index)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error("Could not copy to the clipboard")
    }
  }

  return (
    <div className="flex gap-3">
      <span className="bg-accent text-accent-foreground flex size-8 shrink-0 items-center justify-center rounded-full">
        <Sparkles className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 space-y-3">
        {streaming && (
          <p role="status" className="text-muted-foreground flex items-center gap-2 text-xs">
            <span className="bg-primary size-1.5 animate-pulse rounded-full" aria-hidden />
            {run ? stageLabel(run.stage) : "Working"}…
          </p>
        )}

        {message.content ? (
          <div
            className={cn(
              "text-sm",
              streaming &&
                "after:bg-primary after:ml-0.5 after:inline-block after:h-4 after:w-1.5 after:animate-pulse after:align-middle",
            )}
          >
            <AnswerMarkdown text={message.content} sources={sources} onCite={open} />
          </div>
        ) : streaming ? (
          <div className="space-y-2" aria-hidden>
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : null}

        {message.status === "stopped" && (
          <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
            <Square className="size-3" aria-hidden /> Stopped
          </p>
        )}

        {message.status === "error" && (
          <div
            role="alert"
            className="border-destructive/40 bg-destructive/5 flex items-start gap-2 rounded-lg border p-3 text-sm"
          >
            <AlertCircle className="text-destructive mt-0.5 size-4 shrink-0" aria-hidden />
            <span>{message.error ?? "Something went wrong."}</span>
          </div>
        )}

        {citedSources.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Sources cited">
            {citedSources.map((s) => (
              <li key={s.index}>
                <button
                  type="button"
                  onClick={() => open(s.index)}
                  className="hover:border-primary/60 hover:bg-accent/50 flex max-w-64 items-center gap-1.5 rounded-lg border px-2 py-1 text-xs transition-colors"
                >
                  <span className="bg-accent text-accent-foreground rounded px-1 font-semibold tabular-nums">
                    {s.index}
                  </span>
                  <span className="truncate">{s.filename ?? "document"}</span>
                  {s.page ? <span className="text-muted-foreground">p.{s.page}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        )}

        {!streaming && run?.done && (
          <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
            <Badge variant={run.done.grounded ? "secondary" : "outline"}>
              {run.done.grounded ? "Grounded in your documents" : "No sources cited"}
            </Badge>
            <span>{formatMs(run.done.elapsed_ms)}</span>
            {run.done.iterations > 1 && <span>· {run.done.iterations} search passes</span>}
          </div>
        )}

        <div className="flex items-center gap-1">
          {run && run.plan && (
            <Button
              variant="ghost"
              size="xs"
              aria-expanded={traceOpen}
              onClick={() => setTraceOpen((o) => !o)}
              className="text-muted-foreground"
            >
              Agent trace
              <ChevronDown className={cn("transition-transform", traceOpen && "rotate-180")} aria-hidden />
            </Button>
          )}
          {message.content && !streaming && (
            <Button variant="ghost" size="xs" onClick={copy} className="text-muted-foreground" aria-label="Copy answer">
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy"}
            </Button>
          )}
        </div>

        {traceOpen && <TracePanel run={run} streaming={streaming} />}
      </div>
    </div>
  )
}
