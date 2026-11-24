"use client"

import { memo, useMemo } from "react"
import Markdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

import { CitationChip } from "@/components/chat/citation-chip"
import type { Source } from "@/lib/api/schemas"
import { linkifyCitations } from "@/lib/chat/citations"

type Props = {
  text: string
  sources: Source[]
  onCite?: (index: number) => void
}

function buildComponents(sources: Source[], onCite?: (index: number) => void): Components {
  return {
    a({ href, children }) {
      const m = href?.match(/^#cite-(\d+)$/)
      if (m) {
        const n = Number(m[1])
        return <CitationChip n={n} source={sources.find((s) => s.index === n)} onOpen={onCite} />
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">
          {children}
        </a>
      )
    },
    p: ({ children }) => <p className="mb-3 leading-relaxed last:mb-0">{children}</p>,
    ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
    ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
    h1: ({ children }) => <h3 className="mt-4 mb-2 text-base font-semibold first:mt-0">{children}</h3>,
    h2: ({ children }) => <h3 className="mt-4 mb-2 text-base font-semibold first:mt-0">{children}</h3>,
    h3: ({ children }) => <h4 className="mt-3 mb-1.5 font-semibold first:mt-0">{children}</h4>,
    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
    blockquote: ({ children }) => (
      <blockquote className="text-muted-foreground mb-3 border-l-2 pl-3 italic">{children}</blockquote>
    ),
    code: ({ children, className }) => (
      <code className={className ?? "bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]"}>{children}</code>
    ),
    pre: ({ children }) => (
      <pre className="bg-muted mb-3 overflow-x-auto rounded-lg p-3 font-mono text-[0.85em]">{children}</pre>
    ),
    table: ({ children }) => (
      <div className="mb-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    th: ({ children }) => <th className="border-b px-2 py-1.5 text-left font-medium">{children}</th>,
    td: ({ children }) => <td className="border-b px-2 py-1.5">{children}</td>,
  }
}

/** Renders the answer as markdown, swapping `[n]` markers for clickable citation chips. */
export const AnswerMarkdown = memo(function AnswerMarkdown({ text, sources, onCite }: Props) {
  const markdown = useMemo(
    () => linkifyCitations(text, sources.length ? new Set(sources.map((s) => s.index)) : undefined),
    [text, sources],
  )
  const components = useMemo(() => buildComponents(sources, onCite), [sources, onCite])
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </Markdown>
  )
})
