"use client"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { DocumentInfo } from "@/lib/api/schemas"

type Props = {
  document: DocumentInfo | null
  pending: boolean
  onCancel: () => void
  onConfirm: (doc: DocumentInfo) => void
}

export function ConfirmDeleteDialog({ document, pending, onCancel, onConfirm }: Props) {
  return (
    <Dialog open={document !== null} onOpenChange={(open) => !open && !pending && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this document?</DialogTitle>
          <DialogDescription>
            <strong className="text-foreground">{document?.filename}</strong> and its {document?.chunk_count} indexed
            chunks will be removed from search. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={() => document && onConfirm(document)} disabled={pending}>
            {pending ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
