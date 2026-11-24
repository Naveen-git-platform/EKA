import { beforeEach, describe, expect, it } from "vitest"

import { DEFAULT_API_URL } from "@/lib/config"
import { normalizeApiUrl, useSettings } from "@/lib/store/settings"

beforeEach(() => useSettings.setState({ apiUrl: DEFAULT_API_URL }))

describe("settings store", () => {
  it("normalises trailing slashes and whitespace", () => {
    expect(normalizeApiUrl("  http://x:1///  ")).toBe("http://x:1")
  })

  it("stores a new API URL", () => {
    useSettings.getState().setApiUrl("https://api.example.com/")
    expect(useSettings.getState().apiUrl).toBe("https://api.example.com")
  })

  it("falls back to the default for an empty value", () => {
    useSettings.getState().setApiUrl("   ")
    expect(useSettings.getState().apiUrl).toBe(DEFAULT_API_URL)
  })

  it("resets to the default", () => {
    useSettings.getState().setApiUrl("http://other")
    useSettings.getState().resetApiUrl()
    expect(useSettings.getState().apiUrl).toBe(DEFAULT_API_URL)
  })

  it("persists to localStorage", () => {
    useSettings.getState().setApiUrl("http://persisted:5")
    expect(window.localStorage.getItem("eka-settings")).toContain("http://persisted:5")
  })
})
