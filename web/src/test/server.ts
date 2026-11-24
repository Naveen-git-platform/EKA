import { http, HttpResponse } from "msw"
import { setupServer } from "msw/node"

import { DEFAULT_API_URL } from "@/lib/config"

export const API = DEFAULT_API_URL

export const healthFixture = {
  status: "ok",
  app: "Enterprise Knowledge Agent",
  version: "0.1.0",
  environment: "test",
  llm_provider: "groq",
  llm_model: "openai/gpt-oss-120b",
  llm_configured: true,
  embedding_provider: "sentence-transformers",
  documents: 5,
}

/** Default handlers; individual tests override with `server.use(...)`. */
export const server = setupServer(http.get(`${API}/health`, () => HttpResponse.json(healthFixture)))
