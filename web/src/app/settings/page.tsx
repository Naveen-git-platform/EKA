import type { Metadata } from "next"

import { PageHeader } from "@/components/page-header"
import { SettingsForm } from "@/components/settings/settings-form"

export const metadata: Metadata = { title: "Settings" }

export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6">
      <PageHeader title="Settings" description="Point the app at your backend and pick a theme." />
      <SettingsForm />
    </div>
  )
}
