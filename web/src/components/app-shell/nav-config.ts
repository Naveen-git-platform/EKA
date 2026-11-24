import { FileStack, LayoutDashboard, Settings2, type LucideIcon } from "lucide-react"

export type NavItem = {
  href: string
  label: string
  description: string
  icon: LucideIcon
}

/** Single source of truth for the sidebar, the mobile menu and the command palette. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", description: "What EKA is and how the backend is doing", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", description: "Upload and manage the knowledge base", icon: FileStack },
  { href: "/settings", label: "Settings", description: "Backend URL, theme and connection status", icon: Settings2 },
]

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`)
}
