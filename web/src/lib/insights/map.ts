import type { MapPoint } from "@/lib/api/schemas"
import type { Message } from "@/lib/chat/types"

/** Distinct, colour-blind-friendly-ish hues that read on both dark and light backgrounds. */
export const DOC_PALETTE = [
  "#8b7cf6",
  "#38bdf8",
  "#34d399",
  "#fbbf24",
  "#f472b6",
  "#fb923c",
  "#a3e635",
  "#22d3ee",
] as const

export const HIGHLIGHT_COLOR = "#ffffff"

/** Base point size in world units: big enough to see with a handful of chunks, small enough to stay legible with thousands. */
export function pointSize(count: number): number {
  if (count > 1500) return 0.09
  if (count > 600) return 0.12
  if (count > 100) return 0.17
  return 0.26
}
export const SCENE_RADIUS = 2.4

export function colorForDocs(documents: { doc_id: string }[]): Map<string, string> {
  return new Map(documents.map((d, i) => [d.doc_id, DOC_PALETTE[i % DOC_PALETTE.length]]))
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

export type PointBuffers = {
  positions: Float32Array
  colors: Float32Array
  /** Buffer slot -> index into the original `points` array (hidden documents leave gaps in the original). */
  sourceIndex: number[]
  count: number
}

export type BufferOptions = {
  colors: Map<string, string>
  hiddenDocs?: ReadonlySet<string>
  /** When given, only these chunk ids are included. */
  only?: ReadonlySet<string>
  /** When given, these chunk ids are excluded (used for the dimmed background layer). */
  exclude?: ReadonlySet<string>
  /** Overrides every colour (used for the highlight layer). */
  color?: string
  scale?: number
}

/** Pack points into typed arrays for a THREE.Points geometry. Pure, so it can be tested without WebGL. */
export function buildPointBuffers(points: MapPoint[], opts: BufferOptions): PointBuffers {
  const { colors, hiddenDocs, only, exclude, color, scale = SCENE_RADIUS } = opts
  const keep: number[] = []
  points.forEach((p, i) => {
    if (hiddenDocs?.has(p.doc_id)) return
    if (only && !only.has(p.chunk_id)) return
    if (exclude?.has(p.chunk_id)) return
    keep.push(i)
  })
  const positions = new Float32Array(keep.length * 3)
  const rgb = new Float32Array(keep.length * 3)
  keep.forEach((src, slot) => {
    const p = points[src]
    positions.set([p.x * scale, p.y * scale, p.z * scale], slot * 3)
    rgb.set(hexToRgb(color ?? colors.get(p.doc_id) ?? DOC_PALETTE[0]), slot * 3)
  })
  return { positions, colors: rgb, sourceIndex: keep, count: keep.length }
}

export type RetrievedIds = { retrieved: Set<string>; cited: Set<string> }

/** Chunk ids an assistant answer looked at (every retrieval pass) and the ones it actually cited. */
export function retrievedIds(message: Message | undefined): RetrievedIds {
  const retrieved = new Set<string>()
  const cited = new Set<string>()
  const run = message?.run
  if (!run) return { retrieved, cited }
  for (const r of run.retrievals) for (const c of r.chunks) retrieved.add(c.chunk_id)
  for (const s of run.sources) retrieved.add(s.chunk_id)
  for (const c of run.citations) cited.add(c.chunk_id)
  return { retrieved, cited }
}

export type AnswerOption = { id: string; label: string; message: Message }

/** The most recent finished assistant answers (newest first) that have retrieval data to show on the map. */
export function answerOptions(messages: Message[], conversationTitle: string, limit = 8): AnswerOption[] {
  const out: AnswerOption[] = []
  for (let i = messages.length - 1; i >= 0 && out.length < limit; i--) {
    const m = messages[i]
    if (m.role !== "assistant" || !m.run || m.run.retrievals.length === 0) continue
    const question = messages
      .slice(0, i)
      .reverse()
      .find((x) => x.role === "user")?.content
    const text = (question ?? conversationTitle).replace(/\s+/g, " ").trim()
    out.push({ id: m.id, label: text.length > 70 ? `${text.slice(0, 69)}…` : text, message: m })
  }
  return out
}

/** Evenly spread points on a sphere (Fibonacci lattice): the hero scene's "knowledge orb". */
export function fibonacciSphere(count: number, radius: number): Float32Array {
  const out = new Float32Array(count * 3)
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < count; i++) {
    const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = golden * i
    out.set([Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius], i * 3)
  }
  return out
}

/** True when the browser can create a WebGL context. False on the server, in jsdom and with GPU blocklists. */
export function webglAvailable(): boolean {
  if (typeof document === "undefined") return false
  try {
    const canvas = document.createElement("canvas")
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"))
  } catch {
    return false
  }
}
