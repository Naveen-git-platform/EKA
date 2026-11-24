/**
 * Runtime schemas for every backend payload. They mirror backend/app/api/schemas.py and are used to validate
 * responses, so a backend change shows up as a clear parse error instead of a silent `undefined` in the UI.
 */
import { z } from "zod"

const nullableNumber = z.number().nullable()

// ------------------------------------------------------------------ health
export const HealthSchema = z.object({
  status: z.string(),
  app: z.string(),
  version: z.string(),
  environment: z.string(),
  llm_provider: z.string(),
  llm_model: z.string(),
  llm_configured: z.boolean(),
  embedding_provider: z.string(),
  documents: z.number().nullable().optional(),
})
export type Health = z.infer<typeof HealthSchema>

// ------------------------------------------------------------------ documents
export const DocumentInfoSchema = z.object({
  doc_id: z.string(),
  filename: z.string(),
  file_type: z.string(),
  size_bytes: z.number(),
  chunk_count: z.number(),
  page_count: nullableNumber.optional(),
  created_at: z.string(),
})
export type DocumentInfo = z.infer<typeof DocumentInfoSchema>

export const DocumentListSchema = z.object({
  documents: z.array(DocumentInfoSchema),
  total: z.number(),
  total_chunks: z.number(),
})
export type DocumentList = z.infer<typeof DocumentListSchema>

export const UploadItemSchema = z.object({
  filename: z.string(),
  status: z.enum(["indexed", "replaced", "duplicate", "failed"]),
  doc_id: z.string().nullable().optional(),
  chunk_count: nullableNumber.optional(),
  page_count: nullableNumber.optional(),
  replaced_doc_id: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  error_type: z.string().nullable().optional(),
})
export type UploadItem = z.infer<typeof UploadItemSchema>

export const UploadResponseSchema = z.object({
  results: z.array(UploadItemSchema),
  indexed: z.number().default(0),
  failed: z.number().default(0),
})
export type UploadResponse = z.infer<typeof UploadResponseSchema>

export const DeleteResponseSchema = z.object({ deleted: z.string() })

// ------------------------------------------------------------------ query / agent events
export const ChatMessageSchema = z.object({ role: z.enum(["user", "assistant"]), content: z.string() })
export type ChatMessage = z.infer<typeof ChatMessageSchema>

export type QueryRequest = {
  question: string
  top_k?: number | null
  doc_ids?: string[] | null
  history?: ChatMessage[]
  stream?: boolean
  evaluate?: boolean
}

export const PlanEventSchema = z.object({
  type: z.literal("plan"),
  strategy: z.enum(["direct", "multi_query", "decompose"]),
  standalone_query: z.string(),
  sub_queries: z.array(z.string()),
  reasoning: z.string().default(""),
  fallback: z.boolean().default(false),
})

export const RetrievedChunkSchema = z.object({
  chunk_id: z.string(),
  filename: z.string().nullable().optional(),
  page: nullableNumber.optional(),
  section: z.string().nullable().optional(),
  score: z.number(),
  sources: z.array(z.string()).default([]),
  snippet: z.string(),
})
export type RetrievedChunk = z.infer<typeof RetrievedChunkSchema>

export const RetrievalEventSchema = z.object({
  type: z.literal("retrieval"),
  iteration: z.number(),
  queries: z.array(z.string()),
  chunks: z.array(RetrievedChunkSchema),
  total: z.number(),
})

export const CritiqueEventSchema = z.object({
  type: z.literal("critique"),
  iteration: z.number(),
  sufficient: z.boolean(),
  confidence: z.number(),
  relevance: z.number(),
  coverage: z.number(),
  missing_information: z.string().default(""),
  rewritten_queries: z.array(z.string()).default([]),
  will_retry: z.boolean(),
  reasoning: z.string().default(""),
  degraded: z.boolean().default(false),
})

export const TokenEventSchema = z.object({ type: z.literal("token"), text: z.string() })

export const SourceSchema = z.object({
  index: z.number(),
  chunk_id: z.string(),
  doc_id: z.string().nullable().optional(),
  filename: z.string().nullable().optional(),
  page: nullableNumber.optional(),
  section: z.string().nullable().optional(),
  score: z.number(),
  snippet: z.string(),
  text: z.string(),
})
export type Source = z.infer<typeof SourceSchema>

export const CitationsEventSchema = z.object({
  type: z.literal("citations"),
  citations: z.array(SourceSchema),
  sources: z.array(SourceSchema),
})

export const ErrorEventSchema = z.object({
  type: z.literal("error"),
  stage: z.string().default("unknown"),
  message: z.string(),
})

export const TraceStepSchema = z.object({ node: z.string(), ms: z.number(), ok: z.boolean() })
export type TraceStep = z.infer<typeof TraceStepSchema>

export const DoneEventSchema = z.object({
  type: z.literal("done"),
  ok: z.boolean(),
  answer: z.string(),
  iterations: z.number(),
  elapsed_ms: z.number(),
  trace: z.array(TraceStepSchema).default([]),
  errors: z.array(z.string()).default([]),
  grounded: z.boolean(),
})

export const AgentEventSchema = z.discriminatedUnion("type", [
  PlanEventSchema,
  RetrievalEventSchema,
  CritiqueEventSchema,
  TokenEventSchema,
  CitationsEventSchema,
  ErrorEventSchema,
  DoneEventSchema,
])
export type AgentEvent = z.infer<typeof AgentEventSchema>
export type PlanEvent = z.infer<typeof PlanEventSchema>
export type RetrievalEvent = z.infer<typeof RetrievalEventSchema>
export type CritiqueEvent = z.infer<typeof CritiqueEventSchema>
export type DoneEvent = z.infer<typeof DoneEventSchema>

// ------------------------------------------------------------------ evaluation
export const METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"] as const
export type MetricName = (typeof METRIC_NAMES)[number]

const score = z.number().nullable().optional()

export const EvaluationResultSchema = z.object({
  id: z.string(),
  run_id: z.string().nullable().optional(),
  created_at: z.string(),
  source: z.enum(["api", "batch", "auto"]).default("api"),
  backend: z.string().default("custom"),
  question: z.string(),
  ground_truth: z.string().nullable().optional(),
  answer: z.string(),
  contexts: z.array(z.string()).default([]),
  faithfulness: score,
  answer_relevancy: score,
  context_precision: score,
  context_recall: score,
  overall: score,
  unsupported_claims: z.array(z.string()).default([]),
  errors: z.array(z.string()).default([]),
  latency_ms: score,
  case_id: z.string().nullable().optional(),
  category: z.string().nullable().optional(),
})
export type EvaluationResult = z.infer<typeof EvaluationResultSchema>

export const AggregateSchema = z.record(z.string(), z.number().nullable())
export type Aggregate = z.infer<typeof AggregateSchema>

export const EvaluationListSchema = z.object({
  results: z.array(EvaluationResultSchema),
  total: z.number(),
  aggregate: AggregateSchema,
})
export type EvaluationList = z.infer<typeof EvaluationListSchema>

export const RunInfoSchema = z.object({
  run_id: z.string(),
  created_at: z.string(),
  name: z.string().nullable().optional(),
  status: z.enum(["running", "completed", "failed"]),
  total: z.number(),
  completed: z.number(),
  backend: z.string().default("custom"),
  aggregate: AggregateSchema.default({}),
})
export type RunInfo = z.infer<typeof RunInfoSchema>

export const RunListSchema = z.object({ runs: z.array(RunInfoSchema) })

export type BatchEvaluateRequest = {
  use_sample?: boolean
  cases?: { question: string; ground_truth?: string | null; id?: string | null }[]
  limit?: number | null
  name?: string | null
  top_k?: number | null
}

// ------------------------------------------------------------------ insights
export const BenchmarkSchema = z.object({
  embedder: z.string().optional(),
  k: z.number(),
  n_documents: z.number().optional(),
  n_chunks: z.number().optional(),
  n_questions: z.number().optional(),
  results: z.record(z.string(), z.record(z.string(), z.record(z.string(), z.number()))),
})
export type Benchmark = z.infer<typeof BenchmarkSchema>

export const StatsSchema = z.object({
  documents: z.number(),
  chunks: z.number(),
  file_types: z.record(z.string(), z.number()),
  llm_provider: z.string(),
  llm_model: z.string(),
  embedding_provider: z.string(),
  embedding_model: z.string(),
  evaluation: z.object({
    count: z.number(),
    runs: z.number(),
    aggregate: AggregateSchema,
    avg_latency_ms: z.number().nullable().optional(),
  }),
  benchmark: BenchmarkSchema.nullable().optional(),
})
export type Stats = z.infer<typeof StatsSchema>

export const MapPointSchema = z.object({
  chunk_id: z.string(),
  doc_id: z.string(),
  filename: z.string(),
  page: nullableNumber.optional(),
  section: z.string().nullable().optional(),
  snippet: z.string(),
  x: z.number(),
  y: z.number(),
  z: z.number(),
})
export type MapPoint = z.infer<typeof MapPointSchema>

export const MapResponseSchema = z.object({
  points: z.array(MapPointSchema),
  documents: z.array(z.object({ doc_id: z.string(), filename: z.string(), chunks: z.number() })),
  total: z.number(),
  truncated: z.boolean(),
  explained_variance: z.array(z.number()),
})
export type MapResponse = z.infer<typeof MapResponseSchema>
