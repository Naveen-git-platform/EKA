"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { fetchHealth } from "@/lib/api/health"
import { DEFAULT_API_URL } from "@/lib/config"
import { normalizeApiUrl, useSettings } from "@/lib/store/settings"
import { useIsClient } from "@/lib/use-is-client"
import { cn } from "@/lib/utils"

const FormSchema = z.object({
  apiUrl: z
    .string()
    .trim()
    .min(1, "Enter the backend URL")
    .refine((v) => {
      try {
        const u = new URL(v)
        return u.protocol === "http:" || u.protocol === "https:"
      } catch {
        return false
      }
    }, "Must be a full http(s) URL, e.g. http://localhost:8000"),
})
type FormValues = z.infer<typeof FormSchema>

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const

export function SettingsForm() {
  const apiUrl = useSettings((s) => s.apiUrl)
  const setApiUrl = useSettings((s) => s.setApiUrl)
  const queryClient = useQueryClient()
  const { theme, setTheme } = useTheme()
  const isClient = useIsClient()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(FormSchema), values: { apiUrl } })

  const onSubmit = async ({ apiUrl: next }: FormValues) => {
    const previous = apiUrl
    setApiUrl(next)
    try {
      const health = await fetchHealth()
      toast.success(`Connected to ${health.app} v${health.version}`)
    } catch (err) {
      toast.warning("Saved, but the backend did not answer", {
        description: err instanceof Error ? err.message : undefined,
      })
    }
    if (normalizeApiUrl(next) !== previous) queryClient.invalidateQueries()
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <CardHeader>
            <CardTitle>Backend connection</CardTitle>
            <CardDescription>Where the EKA API is running. Stored in this browser only.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Label htmlFor="apiUrl">API base URL</Label>
            <Input
              id="apiUrl"
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              aria-invalid={!!errors.apiUrl}
              aria-describedby={errors.apiUrl ? "apiUrl-error" : undefined}
              {...register("apiUrl")}
            />
            {errors.apiUrl && (
              <p id="apiUrl-error" role="alert" className="text-destructive text-sm">
                {errors.apiUrl.message}
              </p>
            )}
          </CardContent>
          <CardFooter className="gap-2">
            <Button type="submit" disabled={isSubmitting || !isDirty}>
              Save &amp; test
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setApiUrl(DEFAULT_API_URL)
                reset({ apiUrl: DEFAULT_API_URL })
                queryClient.invalidateQueries()
              }}
              disabled={apiUrl === DEFAULT_API_URL && !isDirty}
            >
              Reset to default
            </Button>
          </CardFooter>
        </form>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Dark is the default. System follows your operating system.</CardDescription>
        </CardHeader>
        <CardContent>
          <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2">
            {THEMES.map(({ value, label, icon: Icon }) => {
              const selected = isClient && theme === value
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setTheme(value)}
                  className={cn(
                    "focus-visible:ring-ring/50 flex flex-col items-center gap-2 rounded-lg border p-3 text-sm transition-colors outline-none focus-visible:ring-3",
                    selected ? "border-primary bg-accent text-accent-foreground" : "hover:bg-muted",
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
