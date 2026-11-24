import { describe, expect, it } from "vitest"

import { highlightBestSentences } from "@/lib/chat/highlight"

const chunk =
  "Leave policy applies to all staff. Full-time employees receive 20 days of paid time off per year. " +
  "Unused days roll over for up to 5 days. Requests go through the HR portal."

const join = (segs: { text: string }[]) => segs.map((s) => s.text).join("")

describe("highlightBestSentences", () => {
  it("highlights the sentence that matches the claim", () => {
    const segs = highlightBestSentences(chunk, "Employees get 20 days of paid time off per year")
    const hits = segs.filter((s) => s.hit).map((s) => s.text.trim())
    expect(hits).toEqual(["Full-time employees receive 20 days of paid time off per year."])
  })

  it("always reproduces the original text exactly", () => {
    for (const claim of ["20 days paid time off", "HR portal requests", "nothing related xyz", ""]) {
      expect(join(highlightBestSentences(chunk, claim))).toBe(chunk)
    }
  })

  it("marks nothing when there is no overlap", () => {
    expect(highlightBestSentences(chunk, "quantum chromodynamics lattice").every((s) => !s.hit)).toBe(true)
  })

  it("marks nothing for an empty claim", () => {
    expect(highlightBestSentences(chunk, "").every((s) => !s.hit)).toBe(true)
  })

  it("can highlight two sentences when both support the claim", () => {
    const segs = highlightBestSentences(
      chunk,
      "20 days paid time off per year and unused days roll over for up to 5 days",
    )
    expect(
      segs
        .filter((s) => s.hit)
        .map((s) => s.text)
        .join(" "),
    ).toContain("roll over")
    expect(
      segs
        .filter((s) => s.hit)
        .map((s) => s.text)
        .join(" "),
    ).toContain("20 days")
  })

  it("respects maxHits", () => {
    const segs = highlightBestSentences("Alpha beta gamma. Alpha beta gamma. Alpha beta gamma.", "alpha beta gamma", 1)
    expect(segs.filter((s) => s.hit)).toHaveLength(1)
  })

  it("handles empty and punctuation-free chunks", () => {
    expect(highlightBestSentences("", "anything")).toEqual([])
    const segs = highlightBestSentences("just one line without punctuation about refunds", "refunds line")
    expect(join(segs)).toBe("just one line without punctuation about refunds")
    expect(segs.some((s) => s.hit)).toBe(true)
  })

  it("merges adjacent segments of the same kind", () => {
    const segs = highlightBestSentences("One thing. Two things. Three things.", "completely unrelated")
    expect(segs).toHaveLength(1)
  })

  it("handles unicode text", () => {
    const text = "Les employés reçoivent vingt jours de congé. Autre phrase sans rapport."
    expect(join(highlightBestSentences(text, "employés reçoivent vingt jours"))).toBe(text)
  })
})
