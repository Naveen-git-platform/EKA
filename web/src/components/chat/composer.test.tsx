import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { Composer } from "@/components/chat/composer"
import { DEFAULT_CHAT_SETTINGS, useChat } from "@/lib/store/chat"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

const docs = [
  { doc_id: "d1", filename: "handbook.md", file_type: "md", size_bytes: 1, chunk_count: 1, created_at: "t" },
  { doc_id: "d2", filename: "faq.txt", file_type: "txt", size_bytes: 1, chunk_count: 1, created_at: "t" },
]

beforeEach(() => {
  useChat.setState({ conversations: [], activeId: null, settings: DEFAULT_CHAT_SETTINGS })
  server.use(http.get(`${API}/documents`, () => HttpResponse.json({ documents: docs, total: 2, total_chunks: 2 })))
})

const box = () => screen.getByLabelText("Your question")

describe("Composer", () => {
  it("sends on Enter and clears the box", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={onSend} onStop={() => {}} />)
    await user.type(box(), "How many PTO days?{Enter}")
    expect(onSend).toHaveBeenCalledWith("How many PTO days?")
    expect(box()).toHaveValue("")
  })

  it("keeps Shift+Enter for new lines", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={onSend} onStop={() => {}} />)
    await user.type(box(), "line one{Shift>}{Enter}{/Shift}line two")
    expect(onSend).not.toHaveBeenCalled()
    expect(box()).toHaveValue("line one\nline two")
  })

  it("does not send blank questions", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={onSend} onStop={() => {}} />)
    expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled()
    await user.type(box(), "   {Enter}")
    expect(onSend).not.toHaveBeenCalled()
  })

  it("trims the question before sending", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={onSend} onStop={() => {}} />)
    await user.type(box(), "  hello  ")
    await user.click(screen.getByRole("button", { name: "Send question" }))
    expect(onSend).toHaveBeenCalledWith("hello")
  })

  it("swaps Send for Stop while streaming and ignores Enter", async () => {
    const onSend = vi.fn()
    const onStop = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming onSend={onSend} onStop={onStop} />)
    expect(screen.queryByRole("button", { name: "Send question" })).not.toBeInTheDocument()
    await user.type(box(), "next question{Enter}")
    expect(onSend).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "Stop generating" }))
    expect(onStop).toHaveBeenCalled()
  })

  it("lets the user scope the search to chosen documents", async () => {
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={() => {}} onStop={() => {}} />)
    await user.click(screen.getByRole("button", { name: "Search options" }))
    expect(await screen.findByText("All documents")).toBeInTheDocument()
    await user.click(await screen.findByRole("checkbox", { name: "faq.txt" }))
    expect(useChat.getState().settings.docIds).toEqual(["d2"])
    expect(screen.getByText("1 selected")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "clear" }))
    expect(useChat.getState().settings.docIds).toEqual([])
  })

  it("sets sources-per-search and background scoring", async () => {
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={() => {}} onStop={() => {}} />)
    await user.click(screen.getByRole("button", { name: "Search options" }))
    await user.selectOptions(screen.getByLabelText("Sources per search"), "8")
    expect(useChat.getState().settings.topK).toBe(8)
    await user.selectOptions(screen.getByLabelText("Sources per search"), "")
    expect(useChat.getState().settings.topK).toBeNull()
    await user.click(screen.getByRole("switch", { name: "Score answers in the background" }))
    await waitFor(() => expect(useChat.getState().settings.evaluate).toBe(true))
  })

  it("shows how many documents are in scope on the options button", async () => {
    useChat.setState({ settings: { ...DEFAULT_CHAT_SETTINGS, docIds: ["d1", "d2"] } })
    renderWithProviders(<Composer streaming={false} onSend={() => {}} onStop={() => {}} />)
    expect(screen.getByRole("button", { name: "Search options" })).toHaveTextContent("2")
  })

  it("explains when there are no documents to scope to", async () => {
    server.use(http.get(`${API}/documents`, () => HttpResponse.json({ documents: [], total: 0, total_chunks: 0 })))
    const user = userEvent.setup()
    renderWithProviders(<Composer streaming={false} onSend={() => {}} onStop={() => {}} />)
    await user.click(screen.getByRole("button", { name: "Search options" }))
    expect(await screen.findByText("No documents indexed yet.")).toBeInTheDocument()
  })
})
