"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { request } from "@/lib/api/client"
import {
  DeleteResponseSchema,
  DocumentListSchema,
  UploadResponseSchema,
  type DocumentList,
  type UploadResponse,
} from "@/lib/api/schemas"
import { useSettings } from "@/lib/store/settings"

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".markdown"] as const
export const MAX_UPLOAD_MB = 25

export const fetchDocuments = (): Promise<DocumentList> => request("/documents", DocumentListSchema)

export function uploadDocuments(files: File[]): Promise<UploadResponse> {
  const form = new FormData()
  for (const f of files) form.append("files", f, f.name)
  return request("/upload", UploadResponseSchema, { method: "POST", body: form })
}

export const deleteDocument = (docId: string) =>
  request(`/documents/${encodeURIComponent(docId)}`, DeleteResponseSchema, { method: "DELETE" })

export const loadSampleDocuments = (): Promise<UploadResponse> =>
  request("/samples/load", UploadResponseSchema, { method: "POST" })

export type FileProblem = { file: File; reason: string }

/** Client-side pre-check so obviously wrong files never leave the browser. */
export function validateFiles(files: File[]): { ok: File[]; rejected: FileProblem[] } {
  const ok: File[] = []
  const rejected: FileProblem[] = []
  for (const file of files) {
    const dot = file.name.lastIndexOf(".")
    const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : ""
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) {
      rejected.push({ file, reason: `Unsupported type. Use ${ACCEPTED_EXTENSIONS.join(", ")}` })
    } else if (file.size === 0) {
      rejected.push({ file, reason: "The file is empty" })
    } else if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      rejected.push({ file, reason: `Larger than ${MAX_UPLOAD_MB} MB` })
    } else {
      ok.push(file)
    }
  }
  return { ok, rejected }
}

function useInvalidateCorpus() {
  const qc = useQueryClient()
  return () => {
    for (const key of ["documents", "health", "stats", "map"]) qc.invalidateQueries({ queryKey: [key] })
  }
}

export function useDocuments() {
  const apiUrl = useSettings((s) => s.apiUrl)
  return useQuery({ queryKey: ["documents", apiUrl], queryFn: fetchDocuments })
}

export function useUploadDocuments() {
  const invalidate = useInvalidateCorpus()
  return useMutation({ mutationFn: uploadDocuments, onSettled: invalidate })
}

export function useDeleteDocument() {
  const invalidate = useInvalidateCorpus()
  return useMutation({ mutationFn: deleteDocument, onSettled: invalidate })
}

export function useLoadSamples() {
  const invalidate = useInvalidateCorpus()
  return useMutation({ mutationFn: loadSampleDocuments, onSettled: invalidate })
}
