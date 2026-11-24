import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"

import {
  deleteDocument,
  fetchDocuments,
  loadSampleDocuments,
  uploadDocuments,
  validateFiles,
} from "@/lib/api/documents"
import { API, server } from "@/test/server"

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name)

describe("validateFiles", () => {
  it("accepts supported types case-insensitively", () => {
    const { ok, rejected } = validateFiles([
      file("a.PDF"),
      file("b.docx"),
      file("c.txt"),
      file("d.md"),
      file("e.markdown"),
    ])
    expect(ok).toHaveLength(5)
    expect(rejected).toEqual([])
  })

  it("rejects unsupported extensions, missing extensions, empty and oversized files", () => {
    const big = file("big.pdf", 1)
    Object.defineProperty(big, "size", { value: 26 * 1024 * 1024 })
    const { ok, rejected } = validateFiles([file("a.exe"), file("noext"), file("empty.txt", 0), big, file("fine.txt")])
    expect(ok.map((f) => f.name)).toEqual(["fine.txt"])
    expect(rejected.map((r) => r.reason)).toEqual([
      expect.stringContaining("Unsupported"),
      expect.stringContaining("Unsupported"),
      "The file is empty",
      "Larger than 25 MB",
    ])
  })
})

describe("document endpoints", () => {
  it("lists documents", async () => {
    server.use(
      http.get(`${API}/documents`, () =>
        HttpResponse.json({
          documents: [
            { doc_id: "d1", filename: "a.pdf", file_type: "pdf", size_bytes: 1, chunk_count: 2, created_at: "t" },
          ],
          total: 1,
          total_chunks: 2,
        }),
      ),
    )
    expect((await fetchDocuments()).documents[0].filename).toBe("a.pdf")
  })

  it("uploads every file under the `files` field", async () => {
    // jsdom's FormData is not undici's, so inspect the request body directly instead of round-tripping it.
    let sent: FormData | undefined
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      sent = init?.body as FormData
      return new Response(JSON.stringify({ results: [], indexed: 2, failed: 0 }), {
        headers: { "Content-Type": "application/json" },
      })
    })
    try {
      const res = await uploadDocuments([file("a.txt"), file("b.md")])
      expect(sent).toBeInstanceOf(FormData)
      expect(sent!.getAll("files").map((f) => (f as File).name)).toEqual(["a.txt", "b.md"])
      expect(res.indexed).toBe(2)
    } finally {
      spy.mockRestore()
    }
  })

  it("surfaces the per-file error when every upload fails", async () => {
    server.use(
      http.post(`${API}/upload`, () =>
        HttpResponse.json(
          { results: [{ filename: "a.txt", status: "failed", error: "empty file" }], indexed: 0, failed: 1 },
          { status: 422 },
        ),
      ),
    )
    await expect(uploadDocuments([file("a.txt")])).rejects.toMatchObject({ message: "a.txt: empty file", status: 422 })
  })

  it("encodes the id when deleting", async () => {
    let path = ""
    server.use(
      http.delete(`${API}/documents/:id`, ({ request }) => {
        path = new URL(request.url).pathname
        return HttpResponse.json({ deleted: "a b" })
      }),
    )
    await deleteDocument("a b")
    expect(path).toBe("/documents/a%20b")
  })

  it("loads the sample documents", async () => {
    server.use(http.post(`${API}/samples/load`, () => HttpResponse.json({ results: [], indexed: 4, failed: 0 })))
    expect((await loadSampleDocuments()).indexed).toBe(4)
  })
})
