"use client"

import { Boxes, FileStack, Files, FlaskConical, Loader2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { ConfirmDeleteDialog } from "@/components/documents/confirm-delete-dialog"
import { DocumentsTable } from "@/components/documents/documents-table"
import { reportUpload, UploadDropzone } from "@/components/documents/upload-dropzone"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useDeleteDocument, useDocuments, useLoadSamples } from "@/lib/api/documents"
import type { DocumentInfo } from "@/lib/api/schemas"
import { formatNumber } from "@/lib/format"

function Stat({ icon: Icon, label, value }: { icon: typeof Files; label: string; value: string }) {
  return (
    <Card size="sm">
      <CardContent className="flex items-center gap-3">
        <span className="bg-accent text-accent-foreground flex size-9 items-center justify-center rounded-lg">
          <Icon className="size-4" aria-hidden />
        </span>
        <div>
          <p className="text-muted-foreground text-xs">{label}</p>
          <p className="text-lg leading-tight font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function DocumentsView() {
  const { data, isPending, isError, error, refetch } = useDocuments()
  const remove = useDeleteDocument()
  const samples = useLoadSamples()
  const [toDelete, setToDelete] = useState<DocumentInfo | null>(null)

  const loadSamples = () =>
    samples.mutate(undefined, {
      onSuccess: reportUpload,
      onError: (err) => toast.error("Could not load the sample documents", { description: err.message }),
    })

  const confirmDelete = (doc: DocumentInfo) =>
    remove.mutate(doc.doc_id, {
      onSuccess: () => {
        toast.success(`Deleted ${doc.filename}`)
        setToDelete(null)
      },
      onError: (err) => toast.error(`Could not delete ${doc.filename}`, { description: err.message }),
    })

  const formats = data ? new Set(data.documents.map((d) => d.file_type)).size : 0

  return (
    <div className="space-y-6">
      <UploadDropzone />

      {isPending ? (
        <div className="space-y-3" aria-label="Loading documents">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="border-destructive/40 bg-destructive/5 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm"
        >
          <span className="text-destructive">{error.message}</span>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : data.documents.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border p-10 text-center">
          <span className="bg-muted text-muted-foreground flex size-11 items-center justify-center rounded-full">
            <FileStack className="size-5" aria-hidden />
          </span>
          <div className="space-y-1">
            <h2 className="font-medium">No documents yet</h2>
            <p className="text-muted-foreground max-w-sm text-sm">
              Upload your own files above, or load the bundled sample company documents to try the agent right away.
            </p>
          </div>
          <Button onClick={loadSamples} disabled={samples.isPending}>
            {samples.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <FlaskConical aria-hidden />}
            Load sample documents
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat icon={Files} label="Documents" value={formatNumber(data.total)} />
            <Stat icon={Boxes} label="Searchable chunks" value={formatNumber(data.total_chunks)} />
            <Stat icon={FileStack} label="File formats" value={formatNumber(formats)} />
          </div>
          <DocumentsTable documents={data.documents} onDelete={setToDelete} />
        </>
      )}

      <ConfirmDeleteDialog
        document={toDelete}
        pending={remove.isPending}
        onCancel={() => setToDelete(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
