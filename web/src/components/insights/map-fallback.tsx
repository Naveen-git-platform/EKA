"use client"

import type { MapPoint } from "@/lib/api/schemas"
import { DOC_PALETTE, type RetrievedIds } from "@/lib/insights/map"

type Props = {
  points: MapPoint[]
  colors: Map<string, string>
  hiddenDocs: ReadonlySet<string>
  highlight: RetrievedIds | null
  onSelect: (index: number | null) => void
}

/** 2D view of the same projection (first two axes) for browsers without WebGL. */
export function MapFallback2D({ points, colors, hiddenDocs, highlight, onSelect }: Props) {
  const dim = !!highlight && highlight.retrieved.size > 0
  return (
    <svg viewBox="-1.1 -1.1 2.2 2.2" className="size-full" role="img" aria-label="2D map of document chunks">
      <rect x="-1.1" y="-1.1" width="2.2" height="2.2" fill="none" />
      {points.map((p, i) => {
        if (hiddenDocs.has(p.doc_id)) return null
        const cited = highlight?.cited.has(p.chunk_id)
        const retrieved = highlight?.retrieved.has(p.chunk_id)
        return (
          <circle
            key={p.chunk_id}
            cx={p.x}
            cy={-p.y}
            r={cited ? 0.045 : retrieved ? 0.032 : 0.016}
            fill={cited ? "#ffffff" : retrieved ? "#fbbf24" : (colors.get(p.doc_id) ?? DOC_PALETTE[0])}
            opacity={dim && !retrieved ? 0.3 : 0.9}
            onClick={() => onSelect(i)}
            className="cursor-pointer"
          >
            <title>{`${p.filename}${p.section ? ` · ${p.section}` : ""}`}</title>
          </circle>
        )
      })}
    </svg>
  )
}
