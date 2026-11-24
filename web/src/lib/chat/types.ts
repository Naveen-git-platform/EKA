import type { CritiqueEvent, DoneEvent, PlanEvent, RetrievalEvent, Source } from "@/lib/api/schemas"

/** Which agent is working right now (or how the run ended). */
export type Stage = "planning" | "retrieving" | "critiquing" | "answering" | "done" | "error"

/** Everything the agents reported while producing one answer. Built incrementally from the SSE events. */
export type RunTrace = {
  stage: Stage
  plan: PlanEvent | null
  retrievals: RetrievalEvent[]
  critiques: CritiqueEvent[]
  sources: Source[]
  citations: Source[]
  done: DoneEvent | null
  errors: { stage: string; message: string }[]
}

export type MessageStatus = "streaming" | "done" | "error" | "stopped"

export type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  status: MessageStatus
  createdAt: number
  run?: RunTrace
  error?: string
}

export type Conversation = {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messages: Message[]
}

export type ChatSettings = {
  /** `null` lets the backend use its default. */
  topK: number | null
  /** Empty means "search every document". */
  docIds: string[]
  /** Ask the backend to score each answer in the background (shows up on the Evaluation page). */
  evaluate: boolean
}
