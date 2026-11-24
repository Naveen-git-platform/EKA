"use client"

import { useRouter } from "next/navigation"
import { useCallback, useEffect, useState } from "react"
import { Command as CommandIcon, Moon, Search, Sun } from "lucide-react"
import { useTheme } from "next-themes"

import { NAV_ITEMS } from "@/components/app-shell/nav-config"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"

/** Ctrl/Cmd+K palette: jump to any page or flip the theme without touching the mouse. */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const router = useRouter()
  const { setTheme } = useTheme()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [])

  const run = useCallback((fn: () => void) => {
    setOpen(false)
    fn()
  }, [])

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="text-muted-foreground hidden w-52 justify-between sm:flex"
        onClick={() => setOpen(true)}
        aria-label="Open command palette"
      >
        <span className="flex items-center gap-2">
          <Search className="size-3.5" /> Search…
        </span>
        <kbd className="bg-muted flex items-center gap-0.5 rounded border px-1.5 text-[0.65rem]">
          <CommandIcon className="size-2.5" />K
        </kbd>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="sm:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open command palette"
      >
        <Search className="size-4" />
      </Button>
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Command palette"
        description="Jump to a page or change theme"
      >
        <Command>
          <CommandInput placeholder="Type a page or action…" />
          <CommandList>
            <CommandEmpty>No results.</CommandEmpty>
            <CommandGroup heading="Go to">
              {NAV_ITEMS.map(({ href, label, description, icon: Icon }) => (
                <CommandItem key={href} value={`${label} ${description}`} onSelect={() => run(() => router.push(href))}>
                  <Icon className="size-4" />
                  <span>{label}</span>
                  <span className="text-muted-foreground ml-auto hidden text-xs md:inline">{description}</span>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup heading="Theme">
              <CommandItem value="light theme" onSelect={() => run(() => setTheme("light"))}>
                <Sun className="size-4" /> Light
              </CommandItem>
              <CommandItem value="dark theme" onSelect={() => run(() => setTheme("dark"))}>
                <Moon className="size-4" /> Dark
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  )
}
