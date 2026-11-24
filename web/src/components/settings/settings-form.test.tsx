import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { SettingsForm } from "@/components/settings/settings-form"
import { DEFAULT_API_URL } from "@/lib/config"
import { useSettings } from "@/lib/store/settings"
import { healthFixture, server } from "@/test/server"
import { renderWithProviders } from "@/test/utils"

const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn() }))
vi.mock("sonner", () => ({ toast, Toaster: () => null }))

beforeEach(() => {
  useSettings.setState({ apiUrl: DEFAULT_API_URL })
  toast.success.mockClear()
  toast.warning.mockClear()
})

const input = () => screen.getByLabelText("API base URL")

describe("SettingsForm", () => {
  it("starts with the current URL and the save button disabled", () => {
    renderWithProviders(<SettingsForm />)
    expect(input()).toHaveValue(DEFAULT_API_URL)
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled()
  })

  it("rejects a value that is not an http(s) URL", async () => {
    const user = userEvent.setup()
    renderWithProviders(<SettingsForm />)
    await user.clear(input())
    await user.type(input(), "not a url")
    await user.click(screen.getByRole("button", { name: /save/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent(/full http\(s\) URL/)
    expect(useSettings.getState().apiUrl).toBe(DEFAULT_API_URL)
  })

  it("saves a valid URL and confirms the connection", async () => {
    server.use(http.get("http://localhost:9100/health", () => HttpResponse.json(healthFixture)))
    const user = userEvent.setup()
    renderWithProviders(<SettingsForm />)
    await user.clear(input())
    await user.type(input(), "http://localhost:9100/")
    await user.click(screen.getByRole("button", { name: /save/i }))
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
    expect(useSettings.getState().apiUrl).toBe("http://localhost:9100")
  })

  it("still saves but warns when the backend does not answer", async () => {
    server.use(http.get("http://localhost:9200/health", () => HttpResponse.error()))
    const user = userEvent.setup()
    renderWithProviders(<SettingsForm />)
    await user.clear(input())
    await user.type(input(), "http://localhost:9200")
    await user.click(screen.getByRole("button", { name: /save/i }))
    await waitFor(() => expect(toast.warning).toHaveBeenCalled())
    expect(useSettings.getState().apiUrl).toBe("http://localhost:9200")
  })

  it("resets to the default URL", async () => {
    useSettings.setState({ apiUrl: "http://custom:1234" })
    const user = userEvent.setup()
    renderWithProviders(<SettingsForm />)
    await user.click(screen.getByRole("button", { name: /reset to default/i }))
    expect(useSettings.getState().apiUrl).toBe(DEFAULT_API_URL)
  })

  it("offers three theme choices", () => {
    renderWithProviders(<SettingsForm />)
    expect(screen.getAllByRole("radio").map((r) => r.textContent)).toEqual(["Light", "Dark", "System"])
  })
})
