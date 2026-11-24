"use client"

import { ArrowUp, SlidersHorizontal, Square } from "lucide-react"
import { useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { useDocuments } from "@/lib/api/documents"
import { useChat } from "@/lib/store/chat"
import { cn } from "@/lib/utils"

const TOP_K_OPTIONS = [3, 5, 8, 12]

type Props = {
  streaming: boolean
  onSend: (question: string) => void
  onStop: () => void
}

function ScopePanel() {
  const { data } = useDocuments()
  const settings = useChat((s) => s.settings)
  const update = useChat((s) => s.updateSettings)
  const docs = data?.documents ?? []

  const toggleDoc = (id: string) =>
    update({
      docIds: settings.docIds.includes(id) ? settings.docIds.filter((d) => d !== id) : [...settings.docIds, id],
    })

  return (
    <div className="bg-card space-y-4 rounded-xl border p-3 text-sm" id="chat-scope">
      <fieldset className="space-y-1.5">
        <legend className="text-muted-foreground mb-1 text-xs font-medium uppercase">Search in</legend>
        {docs.length === 0 ? (
          <p className="text-muted-foreground text-xs">No documents indexed yet.</p>
        ) : (
          <>
            <p className="text-muted-foreground text-xs">
              {settings.docIds.length === 0 ? "All documents" : `${settings.docIds.length} selected`}
              {settings.docIds.length > 0 && (
                <button type="button" className="text-primary ml-2 underline" onClick={() => update({ docIds: [] })}>
                  clear
                </button>
              )}
            </p>
            <ul className="max-h-36 space-y-1 overflow-y-auto pr-1">
              {docs.map((d) => (
                <li key={d.doc_id}>
                  <label className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1">
                    <input
                      type="checkbox"
                      checked={settings.docIds.includes(d.doc_id)}
                      onChange={() => toggleDoc(d.doc_id)}
                      className="accent-primary size-3.5"
                    />
                    <span className="truncate">{d.filename}</span>
                  </label>
                </li>
              ))}
            </ul>
          </>
        )}
      </fieldset>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-center gap-2">
          <Label htmlFor="top-k" className="text-xs">
            Sources per search
          </Label>
          <select
            id="top-k"
            value={settings.topK ?? ""}
            onChange={(e) => update({ topK: e.target.value ? Number(e.target.value) : null })}
            className="bg-background h-7 rounded-md border px-2 text-xs"
          >
            <option value="">Default</option>
            {TOP_K_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="evaluate" checked={settings.evaluate} onCheckedChange={(v) => update({ evaluate: v })} />
          <Label htmlFor="evaluate" className="text-xs">
            Score answers in the background
          </Label>
        </div>
      </div>
    </div>
  )
}

export function Composer({ streaming, onSend, onStop }: Props) {
  const [value, setValue] = useState("")
  const [scopeOpen, setScopeOpen] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)
  const docCount = useChat((s) => s.settings.docIds.length)

  const resize = () => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  const submit = () => {
    const q = value.trim()
    if (!q || streaming) return
    onSend(q)
    setValue("")
    requestAnimationFrame(resize)
  }

  return (
    <div className="space-y-2">
      {scopeOpen && <ScopePanel />}
      <div className="bg-card focus-within:border-ring focus-within:ring-ring/30 flex items-end gap-2 rounded-2xl border p-2 shadow-sm focus-within:ring-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Search options"
          aria-expanded={scopeOpen}
          aria-controls="chat-scope"
          onClick={() => setScopeOpen((o) => !o)}
          className={cn("relative shrink-0", scopeOpen && "bg-muted")}
        >
          <SlidersHorizontal className="size-4" />
          {docCount > 0 && (
            <Badge className="absolute -top-1 -right-1 h-4 min-w-4 justify-center px-1 text-[0.6rem]">{docCount}</Badge>
          )}
        </Button>
        <textarea
          ref={ref}
          value={value}
          rows={1}
          onChange={(e) => {
            setValue(e.target.value)
            resize()
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
          placeholder="Ask about your documents…"
          aria-label="Your question"
          maxLength={2000}
          className="placeholder:text-muted-foreground max-h-50 min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-sm outline-none"
        />
        {streaming ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop generating">
            <Square className="size-4 fill-current" />
          </Button>
        ) : (
          <Button type="button" size="icon" onClick={submit} disabled={!value.trim()} aria-label="Send question">
            <ArrowUp className="size-4" />
          </Button>
        )}
      </div>
      <p className="text-muted-foreground text-center text-[0.7rem]">
        Enter to send · Shift+Enter for a new line · answers can be wrong, check the cited sources
      </p>
    </div>
  )
}
