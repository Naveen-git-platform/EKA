"use client"

import { useReducedMotion } from "framer-motion"
import { Orbit, Pause, Play } from "lucide-react"
import dynamic from "next/dynamic"
import { useMemo, useState } from "react"

import { MapFallback2D } from "@/components/insights/map-fallback"
import { useWebgl } from "@/components/three/use-webgl"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useKnowledgeMap } from "@/lib/api/insights"
import { answerOptions, colorForDocs, retrievedIds } from "@/lib/insights/map"
import { selectActive, useChat } from "@/lib/store/chat"
import { useIsClient } from "@/lib/use-is-client"
import { formatNumber, formatPercent } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { HoverInfo } from "@/components/insights/map-canvas"

const MapCanvas = dynamic(() => import("@/components/insights/map-canvas"), {
  ssr: false,
  loading: () => <Skeleton className="size-full" />,
})

export function KnowledgeMap() {
  const { data, isPending, isError, error, refetch } = useKnowledgeMap()
  const webgl = useWebgl()
  const reduced = useReducedMotion()
  const isClient = useIsClient()
  const conversation = useChat(selectActive)

  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set())
  const [answerId, setAnswerId] = useState("")
  const [hover, setHover] = useState<HoverInfo | null>(null)
  const [pinned, setPinned] = useState<number | null>(null)
  const [rotate, setRotate] = useState<boolean | null>(null) // null = follow the reduced-motion preference

  const colors = useMemo(() => colorForDocs(data?.documents ?? []), [data])
  const options = useMemo(
    () => (isClient && conversation ? answerOptions(conversation.messages, conversation.title) : []),
    [isClient, conversation],
  )
  const chosen = options.find((o) => o.id === answerId)
  const highlight = useMemo(() => (chosen ? retrievedIds(chosen.message) : null), [chosen])
  const autoRotate = rotate ?? !reduced

  const toggleDoc = (id: string) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const hovered = hover && data ? data.points[hover.index] : null
  const selected = pinned !== null && data ? data.points[pinned] : null
  const matched = highlight && data ? data.points.filter((p) => highlight.retrieved.has(p.chunk_id)).length : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Orbit className="size-4" aria-hidden /> Knowledge map
        </CardTitle>
        <CardDescription>
          Every chunk of your documents as a point in 3D; chunks about similar things sit close together. Pick an answer
          to see exactly which chunks the agent looked at (amber) and cited (white).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending ? (
          <Skeleton className="h-[420px] w-full rounded-xl" />
        ) : isError ? (
          <div
            role="alert"
            className="border-destructive/40 bg-destructive/5 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm"
          >
            <span className="text-destructive">{error.message}</span>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        ) : data.points.length === 0 ? (
          <p className="text-muted-foreground flex h-40 items-center justify-center rounded-xl border border-dashed text-sm">
            No chunks are indexed yet. Add documents to see the map.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <ul className="flex flex-wrap gap-1.5" aria-label="Documents">
                {data.documents.map((d) => {
                  const off = hidden.has(d.doc_id)
                  return (
                    <li key={d.doc_id}>
                      <button
                        type="button"
                        aria-pressed={!off}
                        onClick={() => toggleDoc(d.doc_id)}
                        className={cn(
                          "flex max-w-56 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-opacity",
                          off && "opacity-40",
                        )}
                      >
                        <span
                          className="size-2 shrink-0 rounded-full"
                          style={{ background: colors.get(d.doc_id) }}
                          aria-hidden
                        />
                        <span className="truncate">{d.filename}</span>
                        <span className="text-muted-foreground tabular-nums">{d.chunks}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
              <div className="ml-auto flex items-center gap-2">
                <label htmlFor="map-answer" className="text-muted-foreground text-xs">
                  Highlight
                </label>
                <select
                  id="map-answer"
                  value={answerId}
                  onChange={(e) => setAnswerId(e.target.value)}
                  disabled={options.length === 0}
                  className="bg-background h-8 max-w-60 rounded-lg border px-2 text-xs"
                >
                  <option value="">{options.length ? "Nothing" : "Ask a question in Chat first"}</option>
                  {options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </select>
                {webgl && (
                  <Button
                    variant="outline"
                    size="icon-sm"
                    aria-label={autoRotate ? "Pause rotation" : "Start rotation"}
                    onClick={() => setRotate(!autoRotate)}
                  >
                    {autoRotate ? <Pause /> : <Play />}
                  </Button>
                )}
              </div>
            </div>

            <div
              className="bg-muted/20 relative h-[420px] overflow-hidden rounded-xl border"
              role="group"
              aria-label={`3D map of ${formatNumber(data.points.length)} chunks from ${data.documents.length} documents`}
            >
              {webgl ? (
                <MapCanvas
                  points={data.points}
                  colors={colors}
                  hiddenDocs={hidden}
                  highlight={highlight}
                  autoRotate={autoRotate && !hover}
                  onHover={setHover}
                  onSelect={setPinned}
                />
              ) : (
                <MapFallback2D
                  points={data.points}
                  colors={colors}
                  hiddenDocs={hidden}
                  highlight={highlight}
                  onSelect={setPinned}
                />
              )}
              {hovered && hover && (
                <div
                  className="glass pointer-events-none absolute z-10 max-w-64 rounded-lg p-2 text-xs shadow-lg"
                  style={{ left: Math.min(hover.x + 12, 9999), top: hover.y + 12 }}
                  role="tooltip"
                >
                  <p className="font-medium">{hovered.filename}</p>
                  {(hovered.section || hovered.page) && (
                    <p className="text-muted-foreground">
                      {[hovered.section, hovered.page ? `p.${hovered.page}` : null].filter(Boolean).join(" · ")}
                    </p>
                  )}
                  <p className="text-muted-foreground mt-1 line-clamp-3">{hovered.snippet}</p>
                </div>
              )}
              {!webgl && (
                <p className="text-muted-foreground absolute bottom-2 left-3 text-[0.7rem]">
                  2D view: this browser cannot show WebGL.
                </p>
              )}
            </div>

            <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              <span>
                {formatNumber(data.points.length)} of {formatNumber(data.total)} chunks
                {data.truncated ? " (sample)" : ""}
              </span>
              <span title="How much of the variation in the embeddings each axis captures">
                axes explain {data.explained_variance.map((v) => formatPercent(v)).join(" · ")}
              </span>
              {highlight && (
                <span>
                  <Badge variant="secondary">{matched} retrieved</Badge>{" "}
                  <Badge variant="outline">{highlight.cited.size} cited</Badge>
                </span>
              )}
              {webgl && <span>Drag to rotate · scroll to zoom · click a point to pin it</span>}
            </div>

            {selected && (
              <div className="bg-card rounded-xl border p-3 text-sm" aria-live="polite">
                <p className="font-medium">
                  {selected.filename}
                  <span className="text-muted-foreground font-normal">
                    {[selected.section, selected.page ? `p.${selected.page}` : null]
                      .filter(Boolean)
                      .map((s) => ` · ${s}`)
                      .join("")}
                  </span>
                </p>
                <p className="text-muted-foreground mt-1">{selected.snippet}</p>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
