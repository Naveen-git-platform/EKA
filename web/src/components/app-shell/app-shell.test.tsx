import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AppShell } from "@/components/app-shell/app-shell"
import { isActive, NAV_ITEMS } from "@/components/app-shell/nav-config"
import { API, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

const nav = vi.hoisted(() => ({ pathname: "/", push: vi.fn() }))
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push }),
}))

beforeEach(() => {
  nav.pathname = "/"
  nav.push.mockClear()
})

describe("isActive", () => {
  it("matches the root only exactly", () => {
    expect(isActive("/", "/")).toBe(true)
    expect(isActive("/settings", "/")).toBe(false)
  })

  it("matches nested routes", () => {
    expect(isActive("/settings/advanced", "/settings")).toBe(true)
    expect(isActive("/settingsx", "/settings")).toBe(false)
  })
})

describe("AppShell", () => {
  it("renders one link per nav item and marks the current page", () => {
    nav.pathname = "/settings"
    renderWithProviders(<AppShell>content</AppShell>)
    const main = screen.getAllByRole("navigation", { name: "Main" })[0]
    for (const item of NAV_ITEMS) expect(main).toHaveTextContent(item.label)
    expect(screen.getAllByRole("link", { name: "Settings" })[0]).toHaveAttribute("aria-current", "page")
    expect(screen.getAllByRole("link", { name: "Overview" })[0]).not.toHaveAttribute("aria-current")
  })

  it("renders its children inside the main landmark", () => {
    renderWithProviders(<AppShell>hello world</AppShell>)
    expect(screen.getByRole("main")).toHaveTextContent("hello world")
  })

  it("shows the active model when the backend is online", async () => {
    renderWithProviders(<AppShell>x</AppShell>)
    await waitFor(() => expect(screen.getAllByRole("status")[0]).toHaveAttribute("data-state", "online"))
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("groq / openai/gpt-oss-120b")
  })

  it("shows offline when the backend cannot be reached", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.error()))
    renderWithProviders(<AppShell>x</AppShell>)
    await waitFor(() => expect(screen.getAllByRole("status")[0]).toHaveAttribute("data-state", "offline"))
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Backend offline")
  })

  it("opens the command palette with Ctrl+K and navigates", async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppShell>x</AppShell>)
    await user.keyboard("{Control>}k{/Control}")
    const item = await screen.findByRole("option", { name: /Settings/ })
    await user.click(item)
    expect(nav.push).toHaveBeenCalledWith("/settings")
  })
})
