import { create } from "zustand"
import { createJSONStorage, persist } from "zustand/middleware"

import { DEFAULT_API_URL } from "@/lib/config"

export type SettingsState = {
  apiUrl: string
  setApiUrl: (url: string) => void
  resetApiUrl: () => void
}

export function normalizeApiUrl(url: string): string {
  return url.trim().replace(/\/+$/, "")
}

/** localStorage can be missing or throw (private windows, SSR); fall back to in-memory state. */
const safeStorage = createJSONStorage<Pick<SettingsState, "apiUrl">>(() => {
  try {
    if (typeof window !== "undefined" && window.localStorage) return window.localStorage
  } catch {
    /* ignore */
  }
  return { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }
})

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      apiUrl: DEFAULT_API_URL,
      setApiUrl: (url) => set({ apiUrl: normalizeApiUrl(url) || DEFAULT_API_URL }),
      resetApiUrl: () => set({ apiUrl: DEFAULT_API_URL }),
    }),
    { name: "eka-settings", storage: safeStorage, partialize: (s) => ({ apiUrl: s.apiUrl }) },
  ),
)

export const getApiUrl = () => useSettings.getState().apiUrl
