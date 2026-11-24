import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatView } from "@/components/chat/chat-view"
import { MessageBubble } from "@/components/chat/message-bubble"
import { SUGGESTIONS } from "@/components/chat/empty-state"
import type { AgentEvent } from "@/lib/api/schemas"
import { applyEvent, emptyRun } from "@/lib/chat/run"
import type { Message } from "@/lib/chat/types"
import { DEFAULT_CHAT_SETTINGS, useChat } from "@/lib/store/chat"
import { critique, done, happyPath, plan, retrieval, source, sseBody } from "@/test/fixtures"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

vi.mock("next/dynamic", async () => {
  const React = await import("react")
  return { default: () => () => React.createElement("div", { "data-testid": "trace-graph" }) }
})

const sse = (events: AgentEvent[]) =>
  new HttpResponse(sseBody(events), { headers: { "Content-Type": "text/event-stream" } })

const docsResponse = (n: number) =>
  http.get(`${API}/documents`, () =>
    HttpResponse.json({
      documents: Array.from({ length: n }, (_, i) => ({
        doc_id: `d${i}`,
        filename: `doc${i}.md`,
        file_type: "md",
        size_bytes: 1,
        chunk_count: 1,
        created_at: "t",
      })),
      total: n,
      total_chunks: n,
    }),
  )

beforeEach(() => {
  useChat.setState({ conversations: [], activeId: null, settings: DEFAULT_CHAT_SETTINGS })
  server.use(docsResponse(2))
})

describe("ChatView", () => {
  it("greets the user with suggested questions when documents exist", async () => {
    renderWithProviders(<ChatView />)
    expect(await screen.findByText("What would you like to know?")).toBeInTheDocument()
    for (const q of SUGGESTIONS) expect(screen.getByRole("button", { name: q })).toBeInTheDocument()
  })

  it("points to the Documents page when the knowledge base is empty", async () => {
    server.use(docsResponse(0))
    renderWithProviders(<ChatView />)
    expect(await screen.findByRole("link", { name: /add documents/i })).toHaveAttribute("href", "/documents")
    expect(screen.queryByRole("button", { name: SUGGESTIONS[0] })).not.toBeInTheDocument()
  })

  it("asks a suggested question and streams the cited answer", async () => {
    server.use(http.post(`${API}/query`, () => sse(happyPath())))
    const user = userEvent.setup()
    renderWithProviders(<ChatView />)
    await user.click(await screen.findByRole("button", { name: SUGGESTIONS[0] }))
    expect(await screen.findByText(/Employees receive 20 days of PTO/)).toBeInTheDocument()
    expect(screen.getByText(SUGGESTIONS[0], { selector: "div" })).toBeInTheDocument()
    expect(await screen.findByText("Grounded in your documents")).toBeInTheDocument()
    expect(screen.getByRole("list", { name: "Sources cited" })).toHaveTextContent("policy-1.md")
  })

  it("opens the source drawer from a citation chip and highlights the evidence", async () => {
    server.use(http.post(`${API}/query`, () => sse(happyPath())))
    const user = userEvent.setup()
    renderWithProviders(<ChatView />)
    await user.type(await screen.findByLabelText("Your question"), "How many PTO days?{Enter}")
    const chip = await screen.findByRole("button", { name: "Source 1: policy-1.md" })
    await user.click(chip)
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent("policy-1.md")
    expect(within(dialog).getByTestId("source-text").querySelector("mark")).toHaveTextContent("20 days of PTO per year")
  })

  it("expands the agent trace for a finished answer", async () => {
    server.use(http.post(`${API}/query`, () => sse(happyPath())))
    const user = userEvent.setup()
    renderWithProviders(<ChatView />)
    await user.type(await screen.findByLabelText("Your question"), "q{Enter}")
    const toggle = await screen.findByRole("button", { name: /agent trace/i })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByTestId("trace-panel")).toBeInTheDocument()
    expect(screen.getByText("Retrieval pass 1 · 4 chunks")).toBeInTheDocument()
  })

  it("shows a friendly error when the backend is down", async () => {
    server.use(http.post(`${API}/query`, () => HttpResponse.error()))
    const user = userEvent.setup()
    renderWithProviders(<ChatView />)
    await user.type(await screen.findByLabelText("Your question"), "q{Enter}")
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the backend/)
  })

  it("keeps a history of conversations and lets the user switch and delete", async () => {
    server.use(http.post(`${API}/query`, () => sse(happyPath())))
    const user = userEvent.setup()
    renderWithProviders(<ChatView />)
    const input = await screen.findByLabelText("Your question")
    await user.type(input, "first topic{Enter}")
    await screen.findByText("Grounded in your documents")
    await user.click(screen.getAllByRole("button", { name: "New chat" })[0])
    expect(await screen.findByText("What would you like to know?")).toBeInTheDocument()
    await user.type(screen.getByLabelText("Your question"), "second topic{Enter}")
    await screen.findByText("Grounded in your documents")

    const list = screen.getAllByRole("list", { name: "Conversations" })[0]
    expect(within(list).getAllByRole("listitem")).toHaveLength(2)
    await user.click(within(list).getByRole("button", { name: "first topic" }))
    expect(screen.getAllByText("first topic").length).toBeGreaterThan(0)

    await user.click(within(list).getByRole("button", { name: "Delete conversation first topic" }))
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(1))
  })

  it("stops generating when the user presses Stop", async () => {
    server.use(
      http.post(`${API}/query`, () => {
        const enc = new TextEncoder()
        return new HttpResponse(
          new ReadableStream<Uint8Array>({
            start(c) {
              c.enqueue(enc.encode(sseBody([plan, retrieval(), critique(), { type: "token", text: "Working on it" }])))
            },
          }),
          { headers: { "Content-Type": "text/event-stream" } },
        )
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<ChatView />)
    await user.type(await screen.findByLabelText("Your question"), "q{Enter}")
    await user.click(await screen.findByRole("button", { name: "Stop generating" }))
    expect(await screen.findByText("Stopped")).toBeInTheDocument()
    expect(screen.getByText(/Working on it/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Send question" })).toBeInTheDocument()
  })
})

describe("MessageBubble", () => {
  const base: Message = { id: "m", role: "assistant", content: "", status: "streaming", createdAt: 0, run: emptyRun() }
  const render = (m: Message) => renderWithProviders(<MessageBubble message={m} onOpenSource={() => {}} />)

  it("shows the current agent stage while streaming", () => {
    render({ ...base, run: applyEvent(emptyRun(), plan) })
    expect(screen.getByRole("status")).toHaveTextContent("Searching documents")
  })

  it("renders user messages on their own", () => {
    render({ id: "u", role: "user", content: "Hello there", status: "done", createdAt: 0 })
    expect(screen.getByText("Hello there")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("notes when an answer cited no sources", () => {
    const run = [plan, retrieval(), critique(), done({ grounded: false })].reduce(applyEvent, emptyRun())
    render({ ...base, status: "done", content: "I could not find that.", run })
    expect(screen.getByText("No sources cited")).toBeInTheDocument()
  })

  it("only lists sources that the answer actually cites", () => {
    const run = [
      plan,
      { type: "citations", citations: [source(1)], sources: [source(1), source(2)] } as AgentEvent,
      done(),
    ].reduce(applyEvent, emptyRun())
    render({ ...base, status: "done", content: "Answer [1].", run })
    const list = screen.getByRole("list", { name: "Sources cited" })
    expect(within(list).getAllByRole("listitem")).toHaveLength(1)
  })

  it("copies the answer to the clipboard", async () => {
    const user = userEvent.setup() // installs its own clipboard stub, so spy on that one
    const writeText = vi.spyOn(navigator.clipboard, "writeText")
    render({ ...base, status: "done", content: "Copy me" })
    await user.click(screen.getByRole("button", { name: "Copy answer" }))
    expect(writeText).toHaveBeenCalledWith("Copy me")
    expect(await screen.findByText("Copied")).toBeInTheDocument()
  })
})
