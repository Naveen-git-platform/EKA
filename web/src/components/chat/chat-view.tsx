"use client"

import { History, Plus } from "lucide-react"
import { useMemo, useState } from "react"

import { Composer } from "@/components/chat/composer"
import { ChatEmptyState } from "@/components/chat/empty-state"
import { ConversationList } from "@/components/chat/conversation-list"
import { MessageBubble } from "@/components/chat/message-bubble"
import { SourceDrawer } from "@/components/chat/source-drawer"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocuments } from "@/lib/api/documents"
import { citedNumbers } from "@/lib/chat/citations"
import { isConversationStreaming, sendMessage, stopStreaming } from "@/lib/chat/send"
import { selectActive, useChat } from "@/lib/store/chat"
import { useIsClient } from "@/lib/use-is-client"
import { useStickToBottom } from "@/lib/use-stick-to-bottom"

export function ChatView() {
  const isClient = useIsClient()
  const conversations = useChat((s) => s.conversations)
  const activeId = useChat((s) => s.activeId)
  const active = useChat(selectActive)
  const select = useChat((s) => s.selectConversation)
  const remove = useChat((s) => s.deleteConversation)
  const create = useChat((s) => s.newConversation)
  const { data: docs } = useDocuments()

  const [drawer, setDrawer] = useState<{ messageId: string; index: number } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const messages = useMemo(() => active?.messages ?? [], [active])
  const last = messages.at(-1)
  const streaming = isConversationStreaming(active)
  const { ref, onScroll, scrollToBottom } = useStickToBottom<HTMLDivElement>(
    `${messages.length}:${last?.content.length ?? 0}:${last?.status}`,
  )

  const drawerMessage = drawer ? messages.find((m) => m.id === drawer.messageId) : undefined
  const send = (q: string) => {
    scrollToBottom()
    void sendMessage(q)
  }

  if (!isClient) {
    return (
      <div className="flex h-[calc(100dvh-3.5rem)] items-center justify-center" aria-label="Loading chat">
        <Skeleton className="h-24 w-full max-w-xl rounded-2xl" />
      </div>
    )
  }

  const list = (
    <ConversationList
      conversations={conversations}
      activeId={activeId}
      onSelect={(id) => {
        select(id)
        setHistoryOpen(false)
      }}
      onNew={() => {
        create()
        setHistoryOpen(false)
      }}
      onDelete={remove}
    />
  )

  return (
    <div className="flex h-[calc(100dvh-3.5rem)]">
      <aside className="hidden w-64 shrink-0 border-r p-3 lg:block">{list}</aside>

      <section className="flex min-w-0 flex-1 flex-col" aria-label="Conversation">
        <div className="flex items-center gap-2 border-b px-4 py-2 lg:hidden">
          <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
            <SheetTrigger render={<Button variant="ghost" size="sm" />}>
              <History /> History
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-4">
              <SheetHeader className="p-0">
                <SheetTitle>Conversations</SheetTitle>
              </SheetHeader>
              {list}
            </SheetContent>
          </Sheet>
          <span className="text-muted-foreground min-w-0 flex-1 truncate text-sm">{active?.title ?? "New chat"}</span>
          <Button variant="ghost" size="icon-sm" aria-label="New chat" onClick={() => create()}>
            <Plus />
          </Button>
        </div>

        <div ref={ref} onScroll={onScroll} className="flex-1 overflow-y-auto" data-testid="message-scroller">
          {messages.length === 0 ? (
            <ChatEmptyState hasDocuments={(docs?.total ?? 0) > 0 || docs === undefined} onPick={send} />
          ) : (
            <div className="mx-auto max-w-3xl space-y-6 px-4 py-6" role="log" aria-live="polite" aria-label="Messages">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onOpenSource={(messageId, index) => setDrawer({ messageId, index })}
                />
              ))}
            </div>
          )}
        </div>

        <div className="mx-auto w-full max-w-3xl px-4 pb-4">
          <Composer streaming={streaming} onSend={send} onStop={() => stopStreaming()} />
        </div>
      </section>

      <SourceDrawer
        sources={drawerMessage?.run?.sources ?? []}
        cited={drawerMessage ? citedNumbers(drawerMessage.content) : []}
        answer={drawerMessage?.content ?? ""}
        openIndex={drawer?.index ?? null}
        onOpenIndexChange={(index) => setDrawer(index === null ? null : drawer && { ...drawer, index })}
      />
    </div>
  )
}
