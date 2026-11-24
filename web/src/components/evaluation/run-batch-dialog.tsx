"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2, Play } from "lucide-react"
import { useForm, useWatch } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useStartBatch } from "@/lib/api/evaluation"
import type { BatchEvaluateRequest, RunInfo } from "@/lib/api/schemas"
import { MAX_CUSTOM_CASES, parseCases } from "@/lib/eval/metrics"
import { cn } from "@/lib/utils"

const intField = (min: number, max: number, label: string) =>
  z
    .string()
    .trim()
    .refine(
      (v) => v === "" || (/^\d+$/.test(v) && Number(v) >= min && Number(v) <= max),
      `${label} must be a whole number from ${min} to ${max}`,
    )

export const BatchFormSchema = z
  .object({
    source: z.enum(["sample", "custom"]),
    name: z.string().trim().max(100, "Keep the name under 100 characters"),
    limit: intField(1, 100, "Number of questions"),
    topK: intField(1, 20, "Sources per search"),
    cases: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.source !== "custom") return
    const { cases, problems } = parseCases(v.cases)
    if (cases.length === 0) ctx.addIssue({ code: "custom", path: ["cases"], message: "Add at least one question" })
    else if (problems.length > 0)
      ctx.addIssue({ code: "custom", path: ["cases"], message: `Line ${problems[0].line}: ${problems[0].reason}` })
  })
export type BatchForm = z.infer<typeof BatchFormSchema>

export function toRequest(v: BatchForm): BatchEvaluateRequest {
  const topK = v.topK ? Number(v.topK) : null
  const name = v.name || null
  if (v.source === "sample") return { use_sample: true, limit: v.limit ? Number(v.limit) : null, name, top_k: topK }
  return { cases: parseCases(v.cases).cases, name, top_k: topK }
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  disabledReason?: string
  onStarted: (run: RunInfo) => void
}

export function RunBatchDialog({ open, onOpenChange, disabledReason, onStarted }: Props) {
  const start = useStartBatch()
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<BatchForm>({
    resolver: zodResolver(BatchFormSchema),
    defaultValues: { source: "sample", name: "", limit: "", topK: "", cases: "" },
  })
  const source = useWatch({ control, name: "source" })

  const onSubmit = (values: BatchForm) =>
    start.mutate(toRequest(values), {
      onSuccess: (run) => {
        toast.success("Evaluation started", { description: `${run.total} questions are being answered and scored.` })
        onStarted(run)
        onOpenChange(false)
        reset()
      },
      onError: (err) => toast.error("Could not start the evaluation", { description: err.message }),
    })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={<Button disabled={!!disabledReason} title={disabledReason} />}>
        <Play /> Run evaluation
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Run an evaluation</DialogTitle>
          <DialogDescription>
            Each question is answered by the full agent pipeline and then scored by an AI judge. Runs in the background
            and can take a few minutes.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <fieldset className="grid grid-cols-2 gap-2" aria-label="Question source">
            {(
              [
                ["sample", "Sample questions", "36 labelled questions for the bundled documents"],
                ["custom", "My own questions", "Paste questions, optionally with expected answers"],
              ] as const
            ).map(([value, title, hint]) => (
              <label
                key={value}
                className={cn(
                  "has-[:focus-visible]:ring-ring/50 cursor-pointer rounded-lg border p-3 text-sm transition-colors has-[:focus-visible]:ring-3",
                  source === value ? "border-primary bg-accent/40" : "hover:bg-muted/50",
                )}
              >
                <input type="radio" value={value} className="sr-only" {...register("source")} />
                <span className="block font-medium">{title}</span>
                <span className="text-muted-foreground block text-xs">{hint}</span>
              </label>
            ))}
          </fieldset>

          {source === "sample" ? (
            <div className="space-y-1.5">
              <Label htmlFor="limit">How many questions? (blank = all)</Label>
              <Input
                id="limit"
                inputMode="numeric"
                placeholder="e.g. 6 for a quick check"
                aria-invalid={!!errors.limit}
                {...register("limit")}
              />
              {errors.limit && (
                <p role="alert" className="text-destructive text-xs">
                  {errors.limit.message}
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="cases">Questions</Label>
              <textarea
                id="cases"
                rows={6}
                placeholder={"How many PTO days do I get?  ||  20 days per year\nWho approves expenses?"}
                aria-invalid={!!errors.cases}
                className="bg-background focus-visible:ring-ring/50 w-full rounded-lg border p-2.5 font-mono text-xs outline-none focus-visible:ring-3"
                {...register("cases")}
              />
              <p className="text-muted-foreground text-xs">
                One per line. Add <code>||</code> and the expected answer to also score context recall. Up to{" "}
                {MAX_CUSTOM_CASES}.
              </p>
              {errors.cases && (
                <p role="alert" className="text-destructive text-xs">
                  {errors.cases.message}
                </p>
              )}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="name">Run name (optional)</Label>
              <Input
                id="name"
                placeholder="e.g. after prompt change"
                aria-invalid={!!errors.name}
                {...register("name")}
              />
              {errors.name && (
                <p role="alert" className="text-destructive text-xs">
                  {errors.name.message}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="topK">Sources per search (optional)</Label>
              <Input
                id="topK"
                inputMode="numeric"
                placeholder="default"
                aria-invalid={!!errors.topK}
                {...register("topK")}
              />
              {errors.topK && (
                <p role="alert" className="text-destructive text-xs">
                  {errors.topK.message}
                </p>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={start.isPending}>
              {start.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Play aria-hidden />}
              Start
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
