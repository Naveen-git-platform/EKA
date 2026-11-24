import { http, HttpResponse } from "msw"
import { z } from "zod"
import { describe, expect, it } from "vitest"

import { request, streamQuery } from "@/lib/api/client"
import { ApiError, messageFromBody } from "@/lib/api/errors"
import { HealthSchema } from "@/lib/api/schemas"
import { useSettings } from "@/lib/store/settings"
import { API, healthFixture, server } from "@/test/server"

const sse = (events: object[]) =>
  events.map((e) => `event: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join("")

describe("request", () => {
  it("returns validated JSON", async () => {
    await expect(request("/health", HealthSchema)).resolves.toMatchObject({ status: "ok", llm_provider: "groq" })
  })

  it("maps a string `detail` error body", async () => {
    server.use(
      http.get(`${API}/health`, () => HttpResponse.json({ detail: "Service is starting up" }, { status: 503 })),
    )
    await expect(request("/health", HealthSchema)).rejects.toMatchObject({
      message: "Service is starting up",
      status: 503,
    })
  })

  it("flattens FastAPI validation errors", async () => {
    server.use(
      http.get(`${API}/health`, () =>
        HttpResponse.json({ detail: [{ loc: ["body", "question"], msg: "Field required" }] }, { status: 422 }),
      ),
    )
    await expect(request("/health", HealthSchema)).rejects.toThrow("question: Field required")
  })

  it("reports an unreachable backend with the URL", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.error()))
    await expect(request("/health", HealthSchema)).rejects.toThrow(
      /Cannot reach the backend at http:\/\/localhost:8000/,
    )
  })

  it("rejects responses that do not match the schema", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.json({ status: 1 })))
    await expect(request("/health", HealthSchema)).rejects.toBeInstanceOf(ApiError)
  })

  it("rejects non-JSON success bodies", async () => {
    server.use(http.get(`${API}/health`, () => new HttpResponse("<html>", { status: 200 })))
    await expect(request("/health", z.any())).rejects.toThrow(/not valid JSON/)
  })

  it("uses the API URL from settings at call time", async () => {
    useSettings.getState().setApiUrl("http://other-host:9000/")
    server.use(
      http.get("http://other-host:9000/health", () => HttpResponse.json({ ...healthFixture, version: "9.9.9" })),
    )
    await expect(request("/health", HealthSchema)).resolves.toMatchObject({ version: "9.9.9" })
  })
})

describe("messageFromBody", () => {
  it("falls back for unknown shapes", () => {
    expect(messageFromBody(null, "fallback")).toBe("fallback")
    expect(messageFromBody({}, "fallback")).toBe("fallback")
  })

  it("surfaces failed upload results", () => {
    expect(messageFromBody({ results: [{ filename: "a.pdf", error: "empty file" }] }, "x")).toBe("a.pdf: empty file")
  })
})

describe("streamQuery", () => {
  const events = [
    { type: "plan", strategy: "direct", standalone_query: "q", sub_queries: ["q"], reasoning: "", fallback: false },
    { type: "token", text: "Hello " },
    { type: "token", text: "world [1]" },
    {
      type: "done",
      ok: true,
      answer: "Hello world [1]",
      iterations: 1,
      elapsed_ms: 12,
      trace: [],
      errors: [],
      grounded: true,
    },
  ]

  it("yields validated events in order and sends stream=true", async () => {
    let sent: Record<string, unknown> = {}
    server.use(
      http.post(`${API}/query`, async ({ request: r }) => {
        sent = (await r.json()) as Record<string, unknown>
        return new HttpResponse(sse(events), { headers: { "Content-Type": "text/event-stream" } })
      }),
    )
    const got = []
    for await (const ev of streamQuery({ question: "hi", top_k: 3 })) got.push(ev.type)
    expect(got).toEqual(["plan", "token", "token", "done"])
    expect(sent).toMatchObject({ question: "hi", top_k: 3, stream: true })
  })

  it("skips unknown or malformed events instead of failing", async () => {
    const body = sse([{ type: "mystery", a: 1 }, { type: "token" }, ...events.slice(1, 2)])
    server.use(
      http.post(`${API}/query`, () => new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } })),
    )
    const got = []
    for await (const ev of streamQuery({ question: "hi" })) got.push(ev.type)
    expect(got).toEqual(["token"])
  })

  it("throws an ApiError for HTTP errors before streaming", async () => {
    server.use(
      http.post(`${API}/query`, () => HttpResponse.json({ detail: "Service is starting up" }, { status: 503 })),
    )
    await expect(streamQuery({ question: "hi" }).next()).rejects.toMatchObject({ status: 503 })
  })

  it("stops when the caller aborts", async () => {
    server.use(
      http.post(
        `${API}/query`,
        () => new HttpResponse(sse(events), { headers: { "Content-Type": "text/event-stream" } }),
      ),
    )
    const ctrl = new AbortController()
    ctrl.abort()
    await expect(streamQuery({ question: "hi" }, ctrl.signal).next()).rejects.toMatchObject({ name: "AbortError" })
  })
})
