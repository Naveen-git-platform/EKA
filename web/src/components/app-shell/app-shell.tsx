"use client"

import { Menu } from "lucide-react"
import { useState } from "react"

import { BackendStatus } from "@/components/app-shell/backend-status"
import { Brand } from "@/components/app-shell/brand"
import { CommandPalette } from "@/components/app-shell/command-palette"
import { SidebarNav } from "@/components/app-shell/sidebar-nav"
import { ThemeToggle } from "@/components/app-shell/theme-toggle"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"

export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="flex min-h-dvh">
      <aside className="border-sidebar-border bg-sidebar sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-6 border-r p-4 md:flex">
        <Brand />
        <SidebarNav />
        <div className="border-sidebar-border mt-auto rounded-lg border p-3">
          <BackendStatus />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-30 flex h-14 items-center gap-2 border-x-0 border-t-0 px-4">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu" />}>
              <Menu className="size-4" />
            </SheetTrigger>
            <SheetContent side="left" className="w-64 gap-6 p-4">
              <SheetHeader className="p-0">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <Brand />
              </SheetHeader>
              <SidebarNav onNavigate={() => setMenuOpen(false)} />
            </SheetContent>
          </Sheet>
          <div className="md:hidden">
            <Brand />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <BackendStatus className="mr-2 hidden max-w-56 lg:flex" />
            <CommandPalette />
            <ThemeToggle />
          </div>
        </header>
        <main id="content" className="flex-1">
          {children}
        </main>
      </div>
    </div>
  )
}
