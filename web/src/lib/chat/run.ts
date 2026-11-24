import type { AgentEvent } from "@/lib/api/schemas"
import type { RunTrace, Stage } from "@/lib/chat/types"

export function emptyRun(): RunTrace {
  return {
    stage: "planning",
    plan: null,
    retrievals: [],
    critiques: [],
    sources: [],
    citations: [],
    done: null,
    errors: [],
  }
}

/** Pure reducer: fold one agent event into the run trace. Token events only advance the stage; text is handled elsewhere. */
export function applyEvent(run: RunTrace, ev: AgentEvent): RunTrace {
  switch (ev.type) {
    case "plan":
      return { ...run, plan: ev, stage: "retrieving" }
    case "retrieval":
      return { ...run, retrievals: [...run.retrievals, ev], stage: "critiquing" }
    case "critique":
      return { ...run, critiques: [...run.critiques, ev], stage: ev.will_retry ? "retrieving" : "answering" }
    case "token":
      return run.stage === "answering" ? run : { ...run, stage: "answering" }
    case "citations":
      return { ...run, sources: ev.sources, citations: ev.citations }
    case "error":
      return { ...run, errors: [...run.errors, { stage: ev.stage, message: ev.message }] }
    case "done":
      return { ...run, done: ev, stage: ev.ok ? "done" : "error" }
  }
}

const LABELS: Record<Stage, string> = {
  planning: "Planning the search",
  retrieving: "Searching documents",
  critiquing: "Checking the evidence",
  answering: "Writing the answer",
  done: "Done",
  error: "Finished with errors",
}

export const stageLabel = (stage: Stage): string => LABELS[stage]

export const isRunning = (run: RunTrace | undefined): boolean => !!run && run.stage !== "done" && run.stage !== "error"
