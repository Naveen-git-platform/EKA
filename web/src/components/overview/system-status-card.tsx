"use client"

import { AlertTriangle, CheckCircle2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useHealth } from "@/lib/api/health"
import { useSettings } from "@/lib/store/settings"

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border-border/60 flex items-center justify-between gap-4 border-b py-2 text-sm last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate font-medium">{value}</dd>
    </div>
  )
}

export function SystemStatusCard() {
  const apiUrl = useSettings((s) => s.apiUrl)
  const { data, isPending, isError, error } = useHealth()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {isError ? (
            <AlertTriangle className="text-destructive size-4" aria-hidden />
          ) : (
            <CheckCircle2 className="text-success size-4" aria-hidden />
          )}
          System status
        </CardTitle>
        <CardDescription className="truncate">{apiUrl}</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <div className="space-y-2" aria-label="Loading status">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-4/5" />
            <Skeleton className="h-5 w-3/5" />
          </div>
        ) : isError ? (
          <p className="text-destructive text-sm" role="alert">
            {error instanceof Error ? error.message : "The backend is not reachable."}
          </p>
        ) : (
          <dl>
            <Row label="Status" value={<Badge variant="secondary">{data.status}</Badge>} />
            <Row label="Version" value={data.version} />
            <Row label="Environment" value={data.environment} />
            <Row label="Language model" value={`${data.llm_provider} / ${data.llm_model}`} />
            <Row
              label="API key"
              value={
                data.llm_configured ? (
                  "Configured"
                ) : (
                  <span className="text-warning">Missing — answers will use offline mode</span>
                )
              }
            />
            <Row label="Embeddings" value={data.embedding_provider} />
            <Row label="Indexed documents" value={data.documents ?? "—"} />
          </dl>
        )}
      </CardContent>
    </Card>
  )
}
