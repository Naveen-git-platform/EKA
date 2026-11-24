/**
 * Incremental Server-Sent Events parser (TypeScript port of `iter_sse` from the original Streamlit client).
 *
 * Handles comments (`:`), multi-line `data:`, a missing `event:` (falls back to the payload's own `type`), CRLF,
 * frames split across network chunks, and silently skips frames whose data is not a JSON object.
 */
export type SseFrame = { event: string; data: Record<string, unknown> }

export class SseParser {
  private event: string | null = null
  private dataLines: string[] = []

  /** Feed one line (without its line terminator). Returns a frame when a blank line completes one. */
  pushLine(rawLine: string): SseFrame | null {
    const line = rawLine.replace(/[\r\n]+$/, "")
    if (line === "") return this.flush()
    if (line.startsWith(":")) return null
    if (line.startsWith("event:")) {
      this.event = line.slice(6).trim()
    } else if (line.startsWith("data:")) {
      this.dataLines.push(line.slice(5).replace(/^ /, ""))
    }
    return null
  }

  /** Call when the stream ends: emits a trailing frame that had no closing blank line. */
  end(): SseFrame | null {
    return this.flush()
  }

  private flush(): SseFrame | null {
    const name = this.event
    const raw = this.dataLines.join("\n")
    this.event = null
    this.dataLines = []
    if (!raw) return null
    let payload: unknown
    try {
      payload = JSON.parse(raw)
    } catch {
      return null
    }
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) return null
    const data = payload as Record<string, unknown>
    return { event: name || String(data.type ?? "message"), data }
  }
}

/** Parse a complete list of lines (used by tests and non-streaming callers). */
export function* parseSseLines(lines: Iterable<string>): Generator<SseFrame> {
  const parser = new SseParser()
  for (const line of lines) {
    const frame = parser.pushLine(line)
    if (frame) yield frame
  }
  const last = parser.end()
  if (last) yield last
}

/** Read a fetch response body as SSE frames, however the bytes are chunked by the network. */
export async function* iterSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  const parser = new SseParser()
  let buffer = ""
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // A lone trailing "\r" may be the first half of "\r\n": keep it for the next chunk.
      const parts = buffer.split(/\r\n|\n|\r(?!$)/)
      buffer = parts.pop() ?? ""
      for (const line of parts) {
        const frame = parser.pushLine(line)
        if (frame) yield frame
      }
    }
    buffer += decoder.decode()
    if (buffer) {
      const frame = parser.pushLine(buffer)
      if (frame) yield frame
    }
    const last = parser.end()
    if (last) yield last
  } finally {
    reader.releaseLock()
  }
}
