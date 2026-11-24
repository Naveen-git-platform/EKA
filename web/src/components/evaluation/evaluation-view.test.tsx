import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { EvaluationView } from "@/components/evaluation/evaluation-view"
import { BatchFormSchema, toRequest } from "@/components/evaluation/run-batch-dialog"
import { failedResult, result, run } from "@/test/eval-fixtures"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock("sonner", () => ({ toast, Toaster: () => null }))

const aggregate = {
  faithfulness: 1,
  answer_relevancy: 0.86,
  context_precision: 1,
  context_recall: 1,
  overall: 0.9618,
  count: 3,
}

type Setup = { runs?: ReturnType<typeof run>[]; results?: ReturnType<typeof result>[]; docs?: number }
function serve({ runs = [run()], results = [result(), result(), result()], docs = 4 }: Setup = {}) {
  const requested: string[] = []
  server.use(
    http.get(`${API}/evaluations/runs`, () => HttpResponse.json({ runs })),
    http.get(`${API}/evaluations`, ({ request }) => {
      requested.push(new URL(request.url).searchParams.get("run_id") ?? "")
      return HttpResponse.json({ results, total: results.length, aggregate })
    }),
    http.get(`${API}/documents`, () => HttpResponse.json({ documents: [], total: docs, total_chunks: docs })),
  )
  return requested
}

beforeEach(() => Object.values(toast).forEach((m) => m.mockClear()))

describe("EvaluationView", () => {
  it("shows KPIs, charts, runs and answers", async () => {
    serve()
    renderWithProviders(<EvaluationView />)
    expect(await screen.findByRole("group", { name: "Key metrics" })).toHaveTextContent("96%")
    expect(screen.getByRole("list", { name: "Quality profile values" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: /Answers/ })).toBeInTheDocument()
    expect(screen.getAllByText("recheck").length).toBeGreaterThan(0)
  })

  it("shows an empty state when nothing has been evaluated", async () => {
    server.use(
      http.get(`${API}/evaluations/runs`, () => HttpResponse.json({ runs: [] })),
      http.get(`${API}/evaluations`, () => HttpResponse.json({ results: [], total: 0, aggregate: {} })),
      http.get(`${API}/documents`, () => HttpResponse.json({ documents: [], total: 4, total_chunks: 4 })),
    )
    renderWithProviders(<EvaluationView />)
    expect(await screen.findByText("Nothing has been evaluated yet")).toBeInTheDocument()
  })

  it("disables running an evaluation until documents exist", async () => {
    server.use(
      http.get(`${API}/evaluations/runs`, () => HttpResponse.json({ runs: [] })),
      http.get(`${API}/evaluations`, () => HttpResponse.json({ results: [], total: 0, aggregate: {} })),
      http.get(`${API}/documents`, () => HttpResponse.json({ documents: [], total: 0, total_chunks: 0 })),
    )
    renderWithProviders(<EvaluationView />)
    await screen.findByText("Nothing has been evaluated yet")
    await waitFor(() => expect(screen.getByRole("button", { name: /run evaluation/i })).toBeDisabled())
    expect(screen.getByText("Add documents first, then come back.")).toBeInTheDocument()
  })

  it("warns about results that could not be scored", async () => {
    serve({ results: [result(), failedResult(), failedResult()] })
    renderWithProviders(<EvaluationView />)
    const note = await screen.findByRole("note")
    expect(note).toHaveTextContent("2 of 3 results could not be scored at all")
  })

  it("opens the details of a failed answer to show why it failed", async () => {
    serve({ results: [failedResult({ question: "Why did this fail?" })] })
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await user.click(await screen.findByRole("button", { name: /Why did this fail/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid API Key")
  })

  it("filters to one run through the scope selector", async () => {
    const requested = serve({ runs: [run(), run({ run_id: "r2", name: "second" })] })
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await screen.findByRole("group", { name: "Key metrics" })
    await user.selectOptions(screen.getByLabelText("Show"), "r2")
    await waitFor(() => expect(requested).toContain("r2"))
    expect(requested[0]).toBe("")
  })

  it("shows live progress while a run is in progress", async () => {
    serve({ runs: [run({ status: "running", total: 10, completed: 4, name: "live run" })] })
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await screen.findByRole("option", { name: "live run" })
    await user.selectOptions(screen.getByLabelText("Show"), "r1")
    expect(await screen.findByRole("status")).toHaveTextContent("live run is running: 4 of 10 answers scored")
  })

  it("reports a failing backend with a retry button", async () => {
    server.use(
      http.get(`${API}/evaluations/runs`, () =>
        HttpResponse.json({ detail: "Service is starting up" }, { status: 503 }),
      ),
      http.get(`${API}/evaluations`, () => HttpResponse.json({ detail: "Service is starting up" }, { status: 503 })),
      http.get(`${API}/documents`, () => HttpResponse.json({ documents: [], total: 1, total_chunks: 1 })),
    )
    renderWithProviders(<EvaluationView />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Service is starting up")
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
  })
})

describe("batch form", () => {
  it("validates numbers and custom cases", () => {
    const ok = BatchFormSchema.safeParse({ source: "sample", name: "", limit: "6", topK: "", cases: "" })
    expect(ok.success).toBe(true)
    expect(BatchFormSchema.safeParse({ source: "sample", name: "", limit: "0", topK: "", cases: "" }).success).toBe(
      false,
    )
    expect(BatchFormSchema.safeParse({ source: "sample", name: "", limit: "abc", topK: "", cases: "" }).success).toBe(
      false,
    )
    expect(BatchFormSchema.safeParse({ source: "sample", name: "", limit: "", topK: "21", cases: "" }).success).toBe(
      false,
    )
    expect(BatchFormSchema.safeParse({ source: "custom", name: "", limit: "", topK: "", cases: "   " }).success).toBe(
      false,
    )
    const dup = BatchFormSchema.safeParse({ source: "custom", name: "", limit: "", topK: "", cases: "a\nA" })
    expect(dup.success).toBe(false)
    expect(
      BatchFormSchema.safeParse({ source: "custom", name: "", limit: "", topK: "", cases: "a || b\nc" }).success,
    ).toBe(true)
  })

  it("builds the request body", () => {
    expect(toRequest({ source: "sample", name: "", limit: "6", topK: "", cases: "" })).toEqual({
      use_sample: true,
      limit: 6,
      name: null,
      top_k: null,
    })
    expect(toRequest({ source: "custom", name: "mine", limit: "", topK: "8", cases: "q1 || a1\nq2" })).toEqual({
      cases: [
        { question: "q1", ground_truth: "a1" },
        { question: "q2", ground_truth: null },
      ],
      name: "mine",
      top_k: 8,
    })
  })

  it("starts a sample run from the dialog and follows it", async () => {
    serve()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`${API}/evaluate/batch`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          run({ run_id: "new", name: "quick check", status: "running", total: 6, completed: 0 }),
          { status: 202 },
        )
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await user.click(await screen.findByRole("button", { name: /run evaluation/i }))
    const dialog = await screen.findByRole("dialog")
    await user.type(within(dialog).getByLabelText(/How many questions/), "6")
    await user.type(within(dialog).getByLabelText(/Run name/), "quick check")
    await user.click(within(dialog).getByRole("button", { name: "Start" }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Evaluation started", expect.anything()))
    expect(body).toMatchObject({ use_sample: true, limit: 6, name: "quick check" })
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("shows validation errors without calling the backend", async () => {
    serve()
    let called = false
    server.use(http.post(`${API}/evaluate/batch`, () => ((called = true), HttpResponse.json(run()))))
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await user.click(await screen.findByRole("button", { name: /run evaluation/i }))
    const dialog = await screen.findByRole("dialog")
    await user.type(within(dialog).getByLabelText(/How many questions/), "500")
    await user.click(within(dialog).getByRole("button", { name: "Start" }))
    expect(
      await within(dialog).findByText(/Number of questions must be a whole number from 1 to 100/),
    ).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it("reports a backend rejection", async () => {
    serve()
    server.use(
      http.post(`${API}/evaluate/batch`, () =>
        HttpResponse.json({ detail: "No documents indexed yet" }, { status: 409 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await user.click(await screen.findByRole("button", { name: /run evaluation/i }))
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Start" }))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not start the evaluation", {
        description: "No documents indexed yet",
      }),
    )
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("sends custom questions with expected answers", async () => {
    serve()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`${API}/evaluate/batch`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(run({ run_id: "c", total: 2, status: "running", completed: 0 }), { status: 202 })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<EvaluationView />)
    await user.click(await screen.findByRole("button", { name: /run evaluation/i }))
    const dialog = await screen.findByRole("dialog")
    await user.click(within(dialog).getByLabelText(/My own questions/))
    await user.type(within(dialog).getByLabelText("Questions"), "Q one || A one{Enter}Q two")
    await user.click(within(dialog).getByRole("button", { name: "Start" }))
    await waitFor(() => expect(body.cases).toBeDefined())
    expect(body).toMatchObject({
      cases: [
        { question: "Q one", ground_truth: "A one" },
        { question: "Q two", ground_truth: null },
      ],
    })
    expect(body.use_sample).toBeUndefined()
  })
})
