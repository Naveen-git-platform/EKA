import Link from "next/link"
import { Sparkles } from "lucide-react"

import { APP_NAME, APP_SHORT_NAME } from "@/lib/config"

export function Brand() {
  return (
    <Link href="/" className="group flex items-center gap-2.5" aria-label={`${APP_NAME} home`}>
      <span className="glow bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg transition-transform group-hover:scale-105">
        <Sparkles className="size-4" aria-hidden />
      </span>
      <span className="flex flex-col leading-none">
        <span className="text-sm font-semibold tracking-tight">{APP_SHORT_NAME}</span>
        <span className="text-muted-foreground text-[0.65rem]">Knowledge Agent</span>
      </span>
    </Link>
  )
}
