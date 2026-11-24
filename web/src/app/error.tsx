"use client"

import { Button } from "@/components/ui/button"

export default function ErrorPage({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center" role="alert">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="text-muted-foreground text-sm">{error.message || "An unexpected error occurred."}</p>
      <Button onClick={() => retry()}>Try again</Button>
    </div>
  )
}
