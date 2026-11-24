import { beforeEach, describe, expect, it } from "vitest"

import type { Message } from "@/lib/chat/types"
import { DEFAULT_CHAT_SETTINGS, MAX_CONVERSATIONS, selectActive, useChat } from "@/lib/store/chat"

const msg = (id: string, over: Partial<Message> = {}): Message => ({
  id,
  role: "user",
  content: id,
  status: "done",
  createdAt: 1,
  ...over,
})

beforeEach(() => useChat.setState({ conversations: [], activeId: null, settings: DEFAULT_CHAT_SETTINGS }))

describe("chat store", () => {
  it("creates a conversation and makes it active", () => {
    const id = useChat.getState().newConversation()
    expect(useChat.getState().activeId).toBe(id)
    expect(selectActive(useChat.getState())?.title).toBe("New chat")
  })

  it("reuses an empty conversation instead of creating blank ones", () => {
    const a = useChat.getState().newConversation()
    const b = useChat.getState().newConversation()
    expect(b).toBe(a)
    expect(useChat.getState().conversations).toHaveLength(1)
  })

  it("creates a new one once the empty one has messages", () => {
    const a = useChat.getState().newConversation()
    useChat.getState().addMessages(a, [msg("m1")])
    const b = useChat.getState().newConversation()
    expect(b).not.toBe(a)
    expect(useChat.getState().conversations.map((c) => c.id)).toEqual([b, a])
  })

  it("caps the number of stored conversations", () => {
    for (let i = 0; i < MAX_CONVERSATIONS + 5; i++) {
      const id = useChat.getState().newConversation()
      useChat.getState().addMessages(id, [msg(`m${i}`)])
    }
    expect(useChat.getState().conversations).toHaveLength(MAX_CONVERSATIONS)
  })

  it("appends and patches messages by id (object and function patches)", () => {
    const id = useChat.getState().newConversation()
    useChat.getState().addMessages(id, [msg("a", { content: "hel" }), msg("b")])
    useChat.getState().patchMessage(id, "a", (m) => ({ content: m.content + "lo" }))
    useChat.getState().patchMessage(id, "b", { status: "error", error: "x" })
    const [a, b] = selectActive(useChat.getState())!.messages
    expect(a.content).toBe("hello")
    expect(b).toMatchObject({ status: "error", error: "x" })
  })

  it("ignores patches for unknown ids", () => {
    const id = useChat.getState().newConversation()
    useChat.getState().patchMessage(id, "nope", { content: "x" })
    useChat.getState().patchMessage("nope", "nope", { content: "x" })
    expect(selectActive(useChat.getState())!.messages).toEqual([])
  })

  it("selects the next conversation when the active one is deleted", () => {
    const a = useChat.getState().newConversation()
    useChat.getState().addMessages(a, [msg("1")])
    const b = useChat.getState().newConversation()
    useChat.getState().deleteConversation(b)
    expect(useChat.getState().activeId).toBe(a)
    useChat.getState().deleteConversation(a)
    expect(useChat.getState().activeId).toBeNull()
  })

  it("keeps the active conversation when another one is deleted", () => {
    const a = useChat.getState().newConversation()
    useChat.getState().addMessages(a, [msg("1")])
    const b = useChat.getState().newConversation()
    useChat.getState().deleteConversation(a)
    expect(useChat.getState().activeId).toBe(b)
  })

  it("renames and clears", () => {
    const id = useChat.getState().newConversation()
    useChat.getState().setTitle(id, "PTO question")
    expect(selectActive(useChat.getState())?.title).toBe("PTO question")
    useChat.getState().clearAll()
    expect(useChat.getState().conversations).toEqual([])
  })

  it("updates settings partially", () => {
    useChat.getState().updateSettings({ topK: 8 })
    useChat.getState().updateSettings({ evaluate: true })
    expect(useChat.getState().settings).toEqual({ topK: 8, docIds: [], evaluate: true })
  })

  it("persists and marks interrupted streams as stopped on reload", async () => {
    const id = useChat.getState().newConversation()
    useChat
      .getState()
      .addMessages(id, [msg("u"), msg("a", { role: "assistant", status: "streaming", content: "partial" })])
    const raw = window.localStorage.getItem("eka-chat")
    expect(raw).toContain("partial")
    await useChat.persist.rehydrate()
    expect(selectActive(useChat.getState())!.messages[1].status).toBe("stopped")
  })
})
