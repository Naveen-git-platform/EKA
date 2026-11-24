/** Anything that goes wrong talking to the backend. `status` is undefined for network failures. */
export class ApiError extends Error {
  readonly status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

type ValidationItem = { loc?: unknown[]; msg?: string }

/** Turn a FastAPI error body (string detail, validation list, or failed-upload results) into one readable line. */
export function messageFromBody(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback
  const b = body as { detail?: unknown; results?: { filename?: string; error?: string }[] }
  if (Array.isArray(b.detail)) {
    const parts = (b.detail as ValidationItem[]).map((d) => {
      const where = (d.loc ?? []).slice(1).join(".")
      return where ? `${where}: ${d.msg}` : String(d.msg)
    })
    if (parts.length) return parts.join("; ")
  } else if (typeof b.detail === "string" && b.detail) {
    return b.detail
  }
  const failed = (b.results ?? []).filter((r) => r.error).map((r) => `${r.filename}: ${r.error}`)
  return failed.length ? failed.join("; ") : fallback
}
