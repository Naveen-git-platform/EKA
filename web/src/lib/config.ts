/** Default backend URL. Overridable at build time (NEXT_PUBLIC_API_URL) and at runtime from the Settings page. */
export const DEFAULT_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "")

export const APP_NAME = "Enterprise Knowledge Agent"
export const APP_SHORT_NAME = "EKA"
