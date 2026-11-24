"use client"

import { motion } from "framer-motion"
import { BookMarked, GitBranch, SearchCheck, ShieldCheck, type LucideIcon } from "lucide-react"

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type Feature = { icon: LucideIcon; title: string; body: string }

const FEATURES: Feature[] = [
  {
    icon: GitBranch,
    title: "Multi-agent reasoning",
    body: "A Planner breaks the question down, a Retriever searches, a Critic checks the evidence and can send it back for another pass.",
  },
  {
    icon: SearchCheck,
    title: "Hybrid retrieval",
    body: "Dense vectors in Qdrant fused with BM25 keyword search, so both paraphrases and exact identifiers are found.",
  },
  {
    icon: BookMarked,
    title: "Cited answers",
    body: "Every claim points to the chunk it came from. If the documents do not say, the agent says so instead of guessing.",
  },
  {
    icon: ShieldCheck,
    title: "Measured quality",
    body: "Faithfulness, answer relevancy, context precision and recall are scored for every answer you choose to evaluate.",
  },
]

export function FeatureGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {FEATURES.map(({ icon: Icon, title, body }, i) => (
        <motion.div
          key={title}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 * i, duration: 0.35, ease: "easeOut" }}
        >
          <Card className="hover:border-primary/40 h-full transition-colors">
            <CardHeader>
              <span className="bg-accent text-accent-foreground mb-2 flex size-9 items-center justify-center rounded-lg">
                <Icon className="size-4" aria-hidden />
              </span>
              <CardTitle>{title}</CardTitle>
              <CardDescription>{body}</CardDescription>
            </CardHeader>
          </Card>
        </motion.div>
      ))}
    </div>
  )
}
