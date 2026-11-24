"use client"

import { Loader2, UploadCloud } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB, useUploadDocuments, validateFiles } from "@/lib/api/documents"
import type { UploadResponse } from "@/lib/api/schemas"
import { cn } from "@/lib/utils"

export function reportUpload(res: UploadResponse) {
  for (const r of res.results) {
    if (r.status === "indexed") toast.success(`Indexed ${r.filename}`, { description: `${r.chunk_count ?? 0} chunks` })
    else if (r.status === "replaced")
      toast.success(`Updated ${r.filename}`, { description: "Replaced the earlier version" })
    else if (r.status === "duplicate") toast.info(`${r.filename} is already indexed`)
    else toast.error(`Could not index ${r.filename}`, { description: r.error ?? undefined })
  }
}

export function UploadDropzone() {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const upload = useUploadDocuments()

  const handleFiles = (list: FileList | File[] | null) => {
    const files = Array.from(list ?? [])
    if (!files.length) return
    const { ok, rejected } = validateFiles(files)
    for (const { file, reason } of rejected) toast.error(`Skipped ${file.name}`, { description: reason })
    if (!ok.length) return
    upload.mutate(ok, {
      onSuccess: reportUpload,
      onError: (err) => toast.error("Upload failed", { description: err.message }),
    })
    if (inputRef.current) inputRef.current.value = "" // allow picking the same file again
  }

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handleFiles(e.dataTransfer.files)
      }}
      className={cn(
        "focus-within:ring-ring/50 flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors focus-within:ring-3",
        dragging ? "border-primary bg-accent/60" : "hover:border-primary/50 hover:bg-muted/40",
        upload.isPending && "pointer-events-none opacity-70",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="sr-only"
        aria-label="Choose documents to upload"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <span className="bg-accent text-accent-foreground flex size-11 items-center justify-center rounded-full">
        {upload.isPending ? (
          <Loader2 className="size-5 animate-spin" aria-hidden />
        ) : (
          <UploadCloud className="size-5" aria-hidden />
        )}
      </span>
      <span className="space-y-1">
        <span className="block text-sm font-medium">
          {upload.isPending ? "Indexing documents…" : "Drop documents here, or click to browse"}
        </span>
        <span className="text-muted-foreground block text-xs">
          PDF, DOCX, TXT or Markdown · up to {MAX_UPLOAD_MB} MB each
        </span>
      </span>
    </label>
  )
}
