"use client"

import { FileStack, Sparkles } from "lucide-react"
import Link from "next/link"

import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export const SUGGESTIONS = [
  "How many PTO days do full-time employees get each year?",
  "Within how many minutes must an incident commander be assigned for a SEV-1?",
  "How quickly must a suspected security incident be reported?",
  "How long can deleted files be recovered on the Business plan?",
]

type Props = {
  hasDocuments: boolean
  onPick: (question: string) => void
}

export function ChatEmptyState({ hasDocuments, onPick }: Props) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 px-4 py-16 text-center">
      <span className="glow bg-primary text-primary-foreground flex size-12 items-center justify-center rounded-2xl">
        <Sparkles className="size-6" aria-hidden />
      </span>
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight">What would you like to know?</h2>
        <p className="text-muted-foreground text-sm">
          Ask in plain language. The agent plans the search, reads the evidence and answers with sources.
        </p>
      </div>

      {hasDocuments ? (
        <ul className="grid w-full gap-2 sm:grid-cols-2">
          {SUGGESTIONS.map((q) => (
            <li key={q}>
              <button
                type="button"
                onClick={() => onPick(q)}
                className="hover:border-primary/50 hover:bg-accent/40 h-full w-full rounded-xl border p-3 text-left text-sm transition-colors"
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-6">
          <p className="text-muted-foreground text-sm">There are no documents to search yet.</p>
          <Link href="/documents" className={cn(buttonVariants())}>
            <FileStack /> Add documents
          </Link>
        </div>
      )}
    </div>
  )
}
