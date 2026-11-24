"use client"

import { MessageSquare, Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { Conversation } from "@/lib/chat/types"
import { cn } from "@/lib/utils"

type Props = {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
}

export function ConversationList({ conversations, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <Button onClick={onNew} variant="outline" className="w-full justify-start">
        <Plus /> New chat
      </Button>
      {conversations.length === 0 ? (
        <p className="text-muted-foreground px-1 text-xs">Your conversations will appear here.</p>
      ) : (
        <ul className="-mx-1 flex-1 space-y-0.5 overflow-y-auto px-1" aria-label="Conversations">
          {conversations.map((c) => (
            <li key={c.id} className="group relative">
              <button
                type="button"
                onClick={() => onSelect(c.id)}
                aria-current={c.id === activeId ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 pr-9 text-left text-sm transition-colors",
                  c.id === activeId
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "hover:bg-muted text-muted-foreground",
                )}
              >
                <MessageSquare className="size-3.5 shrink-0" aria-hidden />
                <span className="truncate">{c.title}</span>
              </button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Delete conversation ${c.title}`}
                onClick={() => onDelete(c.id)}
                className="hover:text-destructive absolute top-1/2 right-1 -translate-y-1/2 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 focus-visible:opacity-100"
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
