import type { Metadata } from "next"

import { DocumentsView } from "@/components/documents/documents-view"
import { PageHeader } from "@/components/page-header"

export const metadata: Metadata = { title: "Documents" }

export default function DocumentsPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6">
      <PageHeader
        title="Documents"
        description="The knowledge base the agent answers from. Upload files, check how they were chunked, remove what is outdated."
      />
      <DocumentsView />
    </div>
  )
}
