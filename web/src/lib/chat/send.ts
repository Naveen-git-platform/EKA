import type { ChatMessage } from "@/lib/api/schemas"
import { streamQuery } from "@/lib/api/client"
import { applyEvent, emptyRun } from "@/lib/chat/run"
import { normalizeCitationMarkers } from "@/lib/chat/citations"
import type { Conversation, Message } from "@/lib/chat/types"
import { uid, useChat } from "@/lib/store/chat"

const MAX_HISTORY_MESSAGES = 12
const FLUSH_MS = 40
const MAX_TITLE = 56

/** One AbortController per streaming assistant message, so the Stop button can cancel exactly that run. */
const controllers = new Map<string, AbortController>()

export const isConversationStreaming = (c: Conversation | null | undefined): boolean =>
  !!c && c.messages.some((m) => m.status === "streaming")

/** Prior finished turns, trimmed to what the backend accepts, to give the planner follow-up context. */
export function buildHistory(messages: Message[]): ChatMessage[] {
  return messages
    .filter((m) => m.status === "done" && m.content.trim())
    .slice(-MAX_HISTORY_MESSAGES)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 8000) }))
}

export function titleFrom(question: string): string {
  const t = question.replace(/\s+/g, " ").trim()
  return t.length > MAX_TITLE ? `${t.slice(0, MAX_TITLE - 1).trimEnd()}…` : t
}

export function stopStreaming(conversationId?: string) {
  const state = useChat.getState()
  const conv = state.conversations.find((c) => c.id === (conversationId ?? state.activeId))
  for (const m of conv?.messages ?? []) controllers.get(m.id)?.abort()
}

/** Ask a question in the active conversation (creating one if needed) and stream the answer into the store. */
export async function sendMessage(rawQuestion: string): Promise<void> {
  const question = rawQuestion.trim()
  if (!question) return
  const store = useChat.getState()
  const convId =
    store.activeId && store.conversations.some((c) => c.id === store.activeId)
      ? store.activeId
      : store.newConversation()
  const conv = useChat.getState().conversations.find((c) => c.id === convId)!
  if (isConversationStreaming(conv)) return

  const history = buildHistory(conv.messages)
  const now = Date.now()
  const userMsg: Message = { id: uid(), role: "user", content: question, status: "done", createdAt: now }
  const botMsg: Message = {
    id: uid(),
    role: "assistant",
    content: "",
    status: "streaming",
    createdAt: now + 1,
    run: emptyRun(),
  }
  useChat.getState().addMessages(convId, [userMsg, botMsg])
  if (conv.messages.length === 0) useChat.getState().setTitle(convId, titleFrom(question))

  const { settings } = useChat.getState()
  const ctrl = new AbortController()
  controllers.set(botMsg.id, ctrl)

  let pending = ""
  let timer: ReturnType<typeof setTimeout> | null = null
  const patch = (p: Parameters<ReturnType<typeof useChat.getState>["patchMessage"]>[2]) =>
    useChat.getState().patchMessage(convId, botMsg.id, p)
  const flush = () => {
    if (timer) clearTimeout(timer)
    timer = null
    if (!pending) return
    const chunk = pending
    pending = ""
    patch((m) => ({ content: m.content + chunk }))
  }

  try {
    for await (const ev of streamQuery(
      {
        question,
        history,
        top_k: settings.topK,
        doc_ids: settings.docIds.length ? settings.docIds : null,
        evaluate: settings.evaluate,
      },
      ctrl.signal,
    )) {
      if (ev.type === "token") {
        pending += ev.text
        timer ??= setTimeout(flush, FLUSH_MS)
        patch((m) => (m.run ? { run: applyEvent(m.run, ev) } : {}))
        continue
      }
      flush()
      patch((m) => {
        const run = applyEvent(m.run ?? emptyRun(), ev)
        if (ev.type !== "done") return { run }
        const answer = normalizeCitationMarkers(ev.answer || m.content)
        const failed = !ev.ok && !answer.trim()
        return {
          run,
          content: answer,
          status: failed ? "error" : "done",
          error: failed ? (ev.errors[0] ?? "The agent could not produce an answer.") : undefined,
        }
      })
    }
    flush()
    // The stream ended without a `done` event (connection dropped): do not leave the message spinning.
    patch((m) =>
      m.status === "streaming"
        ? {
            status: m.content ? "stopped" : "error",
            error: m.content ? undefined : "The connection closed before an answer arrived.",
          }
        : {},
    )
  } catch (err) {
    flush()
    const aborted = ctrl.signal.aborted || (err instanceof Error && err.name === "AbortError")
    patch((m) => ({
      status: aborted ? "stopped" : "error",
      error: aborted ? undefined : err instanceof Error ? err.message : "Something went wrong",
      run: m.run && { ...m.run, stage: aborted ? m.run.stage : "error" },
    }))
  } finally {
    controllers.delete(botMsg.id)
  }
}
