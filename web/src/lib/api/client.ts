import type { z } from "zod"

import { ApiError, messageFromBody } from "@/lib/api/errors"
import { AgentEventSchema, type AgentEvent, type QueryRequest } from "@/lib/api/schemas"
import { iterSse } from "@/lib/api/sse"
import { getApiUrl } from "@/lib/store/settings"

type RequestOptions = {
  method?: "GET" | "POST" | "DELETE"
  json?: unknown
  body?: FormData
  signal?: AbortSignal
}

async function send(path: string, opts: RequestOptions = {}, accept = "application/json"): Promise<Response> {
  const base = getApiUrl()
  const headers: Record<string, string> = { Accept: accept }
  let body: BodyInit | undefined
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json"
    body = JSON.stringify(opts.json)
  } else if (opts.body) {
    body = opts.body // the browser sets the multipart boundary itself
  }
  let resp: Response
  try {
    resp = await fetch(`${base}${path}`, { method: opts.method ?? "GET", headers, body, signal: opts.signal })
  } catch (err) {
    if (opts.signal?.aborted || (err instanceof Error && err.name === "AbortError")) throw err // caller cancelled
    throw new ApiError(`Cannot reach the backend at ${base}. Is it running?`)
  }
  if (!resp.ok) {
    let parsed: unknown = null
    try {
      parsed = await resp.json()
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(messageFromBody(parsed, `Request failed (HTTP ${resp.status})`), resp.status)
  }
  return resp
}

/** Typed JSON request: the response is validated against `schema`. */
export async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  opts: RequestOptions = {},
): Promise<z.infer<S>> {
  const resp = await send(path, opts)
  let json: unknown
  try {
    json = await resp.json()
  } catch {
    throw new ApiError("The backend returned a response that is not valid JSON", resp.status)
  }
  const parsed = schema.safeParse(json)
  if (!parsed.success) {
    throw new ApiError(
      `Unexpected response from ${path}: ${parsed.error.issues[0]?.message ?? "invalid shape"}`,
      resp.status,
    )
  }
  return parsed.data
}

/** Stream an answer. Yields validated agent events (plan, retrieval, critique, token, citations, error, done). */
export async function* streamQuery(req: QueryRequest, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
  const resp = await send("/query", { method: "POST", json: { ...req, stream: true }, signal }, "text/event-stream")
  if (!resp.body) throw new ApiError("The backend returned an empty stream")
  for await (const frame of iterSse(resp.body)) {
    const parsed = AgentEventSchema.safeParse({ ...frame.data, type: frame.data.type ?? frame.event })
    if (parsed.success) yield parsed.data // unknown / malformed events are skipped, not fatal
  }
}
