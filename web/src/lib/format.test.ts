import { describe, expect, it } from "vitest"

import { formatBytes, formatMs, formatPercent, formatScore } from "@/lib/format"

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [1024, "1.0 KB"],
    [1536, "1.5 KB"],
    [5 * 1024 * 1024, "5.0 MB"],
    [930355, "909 KB"],
  ])("%d -> %s", (input, expected) => expect(formatBytes(input)).toBe(expected))

  it("handles invalid input", () => {
    expect(formatBytes(-1)).toBe("—")
    expect(formatBytes(Number.NaN)).toBe("—")
  })
})

describe("score formatting", () => {
  it("formats percents and scores, with a dash for missing values", () => {
    expect(formatPercent(0.9618, 1)).toBe("96.2%")
    expect(formatPercent(null)).toBe("—")
    expect(formatScore(0.8592)).toBe("0.86")
    expect(formatScore(undefined)).toBe("—")
  })

  it("formats durations", () => {
    expect(formatMs(120.4)).toBe("120 ms")
    expect(formatMs(2500)).toBe("2.5 s")
    expect(formatMs(null)).toBe("—")
  })
})
