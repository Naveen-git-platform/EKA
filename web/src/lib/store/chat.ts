import { create } from "zustand"
import { createJSONStorage, persist } from "zustand/middleware"

import type { ChatSettings, Conversation, Message } from "@/lib/chat/types"

export const MAX_CONVERSATIONS = 30
export const DEFAULT_CHAT_SETTINGS: ChatSettings = { topK: null, docIds: [], evaluate: false }

export const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`

type MessagePatch = Partial<Message> | ((m: Message) => Partial<Message>)

export type ChatState = {
  conversations: Conversation[]
  activeId: string | null
  settings: ChatSettings
  newConversation: () => string
  selectConversation: (id: string | null) => void
  deleteConversation: (id: string) => void
  clearAll: () => void
  setTitle: (id: string, title: string) => void
  addMessages: (conversationId: string, messages: Message[]) => void
  patchMessage: (conversationId: string, messageId: string, patch: MessagePatch) => void
  updateSettings: (patch: Partial<ChatSettings>) => void
}

const touch = (c: Conversation, extra: Partial<Conversation>): Conversation => ({
  ...c,
  ...extra,
  updatedAt: Date.now(),
})

const safeStorage = createJSONStorage<Pick<ChatState, "conversations" | "activeId" | "settings">>(() => {
  try {
    if (typeof window !== "undefined" && window.localStorage) return window.localStorage
  } catch {
    /* ignore */
  }
  return { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }
})

export const useChat = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeId: null,
      settings: DEFAULT_CHAT_SETTINGS,

      newConversation: () => {
        // Reuse an empty conversation instead of piling up blank ones.
        const empty = get().conversations.find((c) => c.messages.length === 0)
        if (empty) {
          set({ activeId: empty.id })
          return empty.id
        }
        const now = Date.now()
        const conversation: Conversation = {
          id: uid(),
          title: "New chat",
          createdAt: now,
          updatedAt: now,
          messages: [],
        }
        set((s) => ({
          conversations: [conversation, ...s.conversations].slice(0, MAX_CONVERSATIONS),
          activeId: conversation.id,
        }))
        return conversation.id
      },

      selectConversation: (id) => set({ activeId: id }),

      deleteConversation: (id) =>
        set((s) => {
          const conversations = s.conversations.filter((c) => c.id !== id)
          return { conversations, activeId: s.activeId === id ? (conversations[0]?.id ?? null) : s.activeId }
        }),

      clearAll: () => set({ conversations: [], activeId: null }),

      setTitle: (id, title) =>
        set((s) => ({ conversations: s.conversations.map((c) => (c.id === id ? touch(c, { title }) : c)) })),

      addMessages: (conversationId, messages) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === conversationId ? touch(c, { messages: [...c.messages, ...messages] }) : c,
          ),
        })),

      patchMessage: (conversationId, messageId, patch) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id !== conversationId
              ? c
              : touch(c, {
                  messages: c.messages.map((m) =>
                    m.id === messageId ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m,
                  ),
                }),
          ),
        })),

      updateSettings: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),
    }),
    {
      name: "eka-chat",
      version: 1,
      storage: safeStorage,
      partialize: (s) => ({ conversations: s.conversations, activeId: s.activeId, settings: s.settings }),
      // A page reload kills any in-flight stream, so persisted "streaming" messages can never finish.
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<ChatState>
        const conversations = (p.conversations ?? current.conversations).map((c) => ({
          ...c,
          messages: c.messages.map((m) => (m.status === "streaming" ? { ...m, status: "stopped" as const } : m)),
        }))
        return { ...current, ...p, conversations, settings: { ...DEFAULT_CHAT_SETTINGS, ...p.settings } }
      },
    },
  ),
)

export const selectActive = (s: ChatState): Conversation | null =>
  s.conversations.find((c) => c.id === s.activeId) ?? null
