import Link from "next/link"

import { buttonVariants } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
      <p className="text-gradient text-6xl font-semibold">404</p>
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground text-sm">That page does not exist. Head back to the overview.</p>
      <Link href="/" className={buttonVariants()}>
        Back to overview
      </Link>
    </div>
  )
}
