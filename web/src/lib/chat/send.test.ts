import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it } from "vitest"

import type { AgentEvent } from "@/lib/api/schemas"
import { buildHistory, isConversationStreaming, sendMessage, stopStreaming, titleFrom } from "@/lib/chat/send"
import type { Message } from "@/lib/chat/types"
import { DEFAULT_CHAT_SETTINGS, selectActive, useChat } from "@/lib/store/chat"
import { critique, done, happyPath, plan, retrieval, source, sseBody } from "@/test/fixtures"
import { API, server } from "@/test/server"

const sseResponse = (events: AgentEvent[]) =>
  new HttpResponse(sseBody(events), { headers: { "Content-Type": "text/event-stream" } })

const active = () => selectActive(useChat.getState())!
const lastBot = () => active().messages.at(-1)!

beforeEach(() => useChat.setState({ conversations: [], activeId: null, settings: DEFAULT_CHAT_SETTINGS }))

describe("buildHistory / titleFrom", () => {
  const m = (role: Message["role"], content: string, status: Message["status"] = "done"): Message => ({
    id: content,
    role,
    content,
    status,
    createdAt: 0,
  })

  it("keeps only finished, non-empty turns and caps the length", () => {
    const msgs = [
      m("user", "q1"),
      m("assistant", "a1"),
      m("user", "q2"),
      m("assistant", "", "streaming"),
      m("assistant", "  ", "done"),
    ]
    expect(buildHistory(msgs).map((x) => x.content)).toEqual(["q1", "a1", "q2"])
    const many = Array.from({ length: 30 }, (_, i) => m(i % 2 ? "assistant" : "user", `t${i}`))
    expect(buildHistory(many)).toHaveLength(12)
    expect(buildHistory(many).at(-1)?.content).toBe("t29")
  })

  it("shortens long titles on a word-ish boundary and collapses whitespace", () => {
    expect(titleFrom("  How   many\n days? ")).toBe("How many days?")
    const long = titleFrom("x".repeat(100))
    expect(long.length).toBeLessThanOrEqual(56)
    expect(long.endsWith("…")).toBe(true)
  })
})

describe("sendMessage", () => {
  it("streams an answer into the store and finalises it", async () => {
    server.use(http.post(`${API}/query`, () => sseResponse(happyPath())))
    await sendMessage("How many PTO days?")
    const conv = active()
    expect(conv.title).toBe("How many PTO days?")
    expect(conv.messages.map((x) => x.role)).toEqual(["user", "assistant"])
    const bot = lastBot()
    expect(bot).toMatchObject({ status: "done", content: "Employees receive 20 days of PTO [1]." })
    expect(bot.run?.stage).toBe("done")
    expect(bot.run?.plan?.strategy).toBe("multi_query")
    expect(bot.run?.citations).toHaveLength(1)
    expect(isConversationStreaming(conv)).toBe(false)
  })

  it("normalises exotic citation markers in the final answer", async () => {
    const events = [plan, retrieval(), critique(), done({ answer: "PTO is 20 days 【1】." })]
    server.use(http.post(`${API}/query`, () => sseResponse(events)))
    await sendMessage("q")
    expect(lastBot().content).toBe("PTO is 20 days [1].")
  })

  it("sends history, scope and options with the request", async () => {
    const bodies: Record<string, unknown>[] = []
    server.use(
      http.post(`${API}/query`, async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>)
        return sseResponse(happyPath())
      }),
    )
    useChat.getState().updateSettings({ topK: 8, docIds: ["d1", "d2"], evaluate: true })
    await sendMessage("first")
    await sendMessage("second")
    expect(bodies[0]).toMatchObject({
      question: "first",
      history: [],
      top_k: 8,
      doc_ids: ["d1", "d2"],
      evaluate: true,
      stream: true,
    })
    expect(bodies[1].history).toEqual([
      { role: "user", content: "first" },
      { role: "assistant", content: "Employees receive 20 days of PTO [1]." },
    ])
  })

  it("sends null for an unrestricted search", async () => {
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`${API}/query`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return sseResponse(happyPath())
      }),
    )
    await sendMessage("q")
    expect(body).toMatchObject({ top_k: null, doc_ids: null, evaluate: false })
  })

  it("ignores blank questions", async () => {
    await sendMessage("   ")
    expect(useChat.getState().conversations).toEqual([])
  })

  it("does not start a second run while one is streaming", async () => {
    const id = useChat.getState().newConversation()
    useChat.getState().addMessages(id, [{ id: "b", role: "assistant", content: "", status: "streaming", createdAt: 0 }])
    await sendMessage("another")
    expect(active().messages).toHaveLength(1)
  })

  it("keeps the conversation title from the first question only", async () => {
    server.use(http.post(`${API}/query`, () => sseResponse(happyPath())))
    await sendMessage("first question")
    await sendMessage("second question")
    expect(active().title).toBe("first question")
  })

  it("marks the message as an error when the request fails", async () => {
    server.use(
      http.post(`${API}/query`, () => HttpResponse.json({ detail: "Service is starting up" }, { status: 503 })),
    )
    await sendMessage("q")
    expect(lastBot()).toMatchObject({ status: "error", error: "Service is starting up" })
  })

  it("explains an unreachable backend", async () => {
    server.use(http.post(`${API}/query`, () => HttpResponse.error()))
    await sendMessage("q")
    expect(lastBot().status).toBe("error")
    expect(lastBot().error).toMatch(/Cannot reach the backend/)
  })

  it("reports an agent failure that produced no answer", async () => {
    const events = [
      plan,
      { type: "error", stage: "answer", message: "model down" } as AgentEvent,
      done({ ok: false, answer: "", errors: ["answer: model down"] }),
    ]
    server.use(http.post(`${API}/query`, () => sseResponse(events)))
    await sendMessage("q")
    expect(lastBot()).toMatchObject({ status: "error", error: "answer: model down" })
    expect(lastBot().run?.errors).toEqual([{ stage: "answer", message: "model down" }])
  })

  it("keeps a partial answer when the stream ends without a done event", async () => {
    const events: AgentEvent[] = [plan, retrieval(), critique(), { type: "token", text: "Half an answer" }]
    server.use(http.post(`${API}/query`, () => sseResponse(events)))
    await sendMessage("q")
    expect(lastBot()).toMatchObject({ status: "stopped", content: "Half an answer" })
  })

  it("marks an empty dropped stream as an error", async () => {
    server.use(http.post(`${API}/query`, () => sseResponse([plan])))
    await sendMessage("q")
    expect(lastBot()).toMatchObject({ status: "error", error: "The connection closed before an answer arrived." })
  })

  it("stop() cancels the run and keeps what was already written", async () => {
    server.use(
      http.post(`${API}/query`, () => {
        const enc = new TextEncoder()
        const stream = new ReadableStream<Uint8Array>({
          start(c) {
            c.enqueue(enc.encode(sseBody([plan, retrieval(), critique(), { type: "token", text: "Partial" }])))
            // never closes: simulates a slow model
          },
        })
        return new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } })
      }),
    )
    const run = sendMessage("q")
    await new Promise((r) => setTimeout(r, 150))
    expect(isConversationStreaming(active())).toBe(true)
    stopStreaming()
    await run
    expect(lastBot()).toMatchObject({ status: "stopped", content: "Partial" })
    expect(lastBot().error).toBeUndefined()
  })

  it("passes sources through for the drawer", async () => {
    const events: AgentEvent[] = [
      plan,
      retrieval(),
      critique(),
      { type: "citations", citations: [source(2)], sources: [source(1), source(2)] },
      done(),
    ]
    server.use(http.post(`${API}/query`, () => sseResponse(events)))
    await sendMessage("q")
    expect(lastBot().run?.sources.map((s) => s.index)).toEqual([1, 2])
  })
})
