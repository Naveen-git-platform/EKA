import { screen } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { FeatureGrid } from "@/components/overview/feature-grid"
import { SystemStatusCard } from "@/components/overview/system-status-card"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

describe("SystemStatusCard", () => {
  it("shows backend details once loaded", async () => {
    renderWithProviders(<SystemStatusCard />)
    expect(await screen.findByText("groq / openai/gpt-oss-120b")).toBeInTheDocument()
    expect(screen.getByText("Configured")).toBeInTheDocument()
    expect(screen.getByText("5")).toBeInTheDocument()
  })

  it("warns when no API key is configured", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.json({ ...healthFixtureBase(), llm_configured: false })))
    renderWithProviders(<SystemStatusCard />)
    expect(await screen.findByText(/Missing/)).toBeInTheDocument()
  })

  it("explains when the backend is unreachable", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.error()))
    renderWithProviders(<SystemStatusCard />)
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the backend/)
  })
})

describe("FeatureGrid", () => {
  it("lists the four capabilities", () => {
    renderWithProviders(<FeatureGrid />)
    for (const t of ["Multi-agent reasoning", "Hybrid retrieval", "Cited answers", "Measured quality"])
      expect(screen.getByText(t)).toBeInTheDocument()
  })
})

function healthFixtureBase() {
  return {
    status: "ok",
    app: "EKA",
    version: "0.1.0",
    environment: "test",
    llm_provider: "groq",
    llm_model: "m",
    llm_configured: true,
    embedding_provider: "e",
    documents: 1,
  }
}
