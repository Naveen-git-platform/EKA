import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { sortDocuments } from "@/components/documents/documents-table"
import { DocumentsView } from "@/components/documents/documents-view"
import type { DocumentInfo } from "@/lib/api/schemas"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock("sonner", () => ({ toast, Toaster: () => null }))

const doc = (over: Partial<DocumentInfo>): DocumentInfo => ({
  doc_id: "d1",
  filename: "handbook.md",
  file_type: "md",
  size_bytes: 2048,
  chunk_count: 5,
  page_count: null,
  created_at: "2026-11-20T10:00:00+00:00",
  ...over,
})

const DOCS = [
  doc({ doc_id: "d1", filename: "handbook.md", chunk_count: 5, created_at: "2026-11-20T10:00:00+00:00" }),
  doc({
    doc_id: "d2",
    filename: "runbook.pdf",
    file_type: "pdf",
    page_count: 2,
    chunk_count: 2,
    size_bytes: 3467,
    created_at: "2026-11-22T10:00:00+00:00",
  }),
  doc({ doc_id: "d3", filename: "faq.txt", file_type: "txt", chunk_count: 3, created_at: "2026-11-21T10:00:00+00:00" }),
]

const listing = (documents: DocumentInfo[]) =>
  http.get(`${API}/documents`, () =>
    HttpResponse.json({
      documents,
      total: documents.length,
      total_chunks: documents.reduce((n, d) => n + d.chunk_count, 0),
    }),
  )

beforeEach(() => Object.values(toast).forEach((m) => m.mockClear()))

describe("sortDocuments", () => {
  it("sorts by text, number and date in both directions", () => {
    expect(sortDocuments(DOCS, "filename", "asc").map((d) => d.doc_id)).toEqual(["d3", "d1", "d2"])
    expect(sortDocuments(DOCS, "chunk_count", "desc").map((d) => d.doc_id)).toEqual(["d1", "d3", "d2"])
    expect(sortDocuments(DOCS, "created_at", "desc").map((d) => d.doc_id)).toEqual(["d2", "d3", "d1"])
  })

  it("does not mutate its input", () => {
    const copy = [...DOCS]
    sortDocuments(DOCS, "filename", "asc")
    expect(DOCS).toEqual(copy)
  })
})

describe("DocumentsView", () => {
  it("shows totals and every document, newest first", async () => {
    server.use(listing(DOCS))
    renderWithProviders(<DocumentsView />)
    expect(await screen.findByText("runbook.pdf")).toBeInTheDocument()
    const rows = screen.getAllByRole("row").slice(1)
    expect(rows.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual([
      expect.stringContaining("runbook.pdf"),
      expect.stringContaining("faq.txt"),
      expect.stringContaining("handbook.md"),
    ])
    expect(screen.getByText("Searchable chunks").nextSibling).toHaveTextContent("10")
  })

  it("filters by name and says when nothing matches", async () => {
    server.use(listing(DOCS))
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    await screen.findByText("runbook.pdf")
    await user.type(screen.getByLabelText("Filter documents by name"), "faq")
    expect(screen.queryByText("runbook.pdf")).not.toBeInTheDocument()
    expect(screen.getByText("faq.txt")).toBeInTheDocument()
    await user.clear(screen.getByLabelText("Filter documents by name"))
    await user.type(screen.getByLabelText("Filter documents by name"), "zzz")
    expect(screen.getByText(/No documents match/)).toBeInTheDocument()
  })

  it("re-sorts when a column header is clicked", async () => {
    server.use(listing(DOCS))
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    await screen.findByText("runbook.pdf")
    await user.click(screen.getByRole("button", { name: "Document" }))
    const first = screen.getAllByRole("row")[1]
    expect(first).toHaveTextContent("faq.txt")
    expect(screen.getByRole("columnheader", { name: "Document" })).toHaveAttribute("aria-sort", "ascending")
  })

  it("offers sample documents when the knowledge base is empty", async () => {
    let loaded = false
    server.use(
      http.get(`${API}/documents`, () =>
        HttpResponse.json(
          loaded ? { documents: DOCS, total: 3, total_chunks: 10 } : { documents: [], total: 0, total_chunks: 0 },
        ),
      ),
      http.post(`${API}/samples/load`, () => {
        loaded = true
        return HttpResponse.json({
          results: [{ filename: "handbook.md", status: "indexed", chunk_count: 5 }],
          indexed: 1,
          failed: 0,
        })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    await user.click(await screen.findByRole("button", { name: /load sample documents/i }))
    expect(await screen.findByText("runbook.pdf")).toBeInTheDocument()
    expect(toast.success).toHaveBeenCalledWith("Indexed handbook.md", expect.anything())
  })

  it("confirms before deleting and removes the document", async () => {
    let docs = [...DOCS]
    server.use(
      http.get(`${API}/documents`, () => HttpResponse.json({ documents: docs, total: docs.length, total_chunks: 1 })),
      http.delete(`${API}/documents/:id`, ({ params }) => {
        docs = docs.filter((d) => d.doc_id !== params.id)
        return HttpResponse.json({ deleted: params.id })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    await user.click(await screen.findByRole("button", { name: "Delete faq.txt" }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent("faq.txt")
    await user.click(within(dialog).getByRole("button", { name: "Delete" }))
    await waitFor(() => expect(screen.queryByText("faq.txt")).not.toBeInTheDocument())
    expect(toast.success).toHaveBeenCalledWith("Deleted faq.txt")
  })

  it("cancelling the dialog deletes nothing", async () => {
    server.use(listing(DOCS))
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    await user.click(await screen.findByRole("button", { name: "Delete faq.txt" }))
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.getByText("faq.txt")).toBeInTheDocument()
  })

  it("shows an error with a retry button when the backend fails", async () => {
    let fail = true
    server.use(
      http.get(`${API}/documents`, () =>
        fail
          ? HttpResponse.json({ detail: "Service is starting up" }, { status: 503 })
          : HttpResponse.json({ documents: DOCS, total: 3, total_chunks: 10 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Service is starting up")
    fail = false
    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("runbook.pdf")).toBeInTheDocument()
  })

  it("uploads picked files and reports each result", async () => {
    server.use(
      listing(DOCS),
      http.post(`${API}/upload`, () =>
        HttpResponse.json({
          results: [
            { filename: "new.txt", status: "indexed", chunk_count: 3 },
            { filename: "same.txt", status: "duplicate" },
            { filename: "bad.pdf", status: "failed", error: "corrupt" },
          ],
          indexed: 2,
          failed: 1,
        }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<DocumentsView />)
    await screen.findByText("runbook.pdf")
    await user.upload(screen.getByLabelText("Choose documents to upload"), [
      new File(["x"], "new.txt"),
      new File(["x"], "same.txt"),
      new File(["x"], "bad.pdf"),
    ])
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not index bad.pdf", { description: "corrupt" }))
    expect(toast.success).toHaveBeenCalledWith("Indexed new.txt", { description: "3 chunks" })
    expect(toast.info).toHaveBeenCalledWith("same.txt is already indexed")
  })

  it("rejects unsupported files without calling the backend", async () => {
    server.use(listing(DOCS))
    const user = userEvent.setup({ applyAccept: false })
    renderWithProviders(<DocumentsView />)
    await screen.findByText("runbook.pdf")
    await user.upload(screen.getByLabelText("Choose documents to upload"), new File(["x"], "virus.exe"))
    expect(toast.error).toHaveBeenCalledWith(
      "Skipped virus.exe",
      expect.objectContaining({ description: expect.stringContaining("Unsupported") }),
    )
  })
})
