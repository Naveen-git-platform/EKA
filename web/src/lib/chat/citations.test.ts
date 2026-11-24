import { describe, expect, it } from "vitest"

import { citedNumbers, claimForCitation, linkifyCitations, normalizeCitationMarkers } from "@/lib/chat/citations"

describe("normalizeCitationMarkers", () => {
  it.each([
    ["Answer 【1】.", "Answer [1]."],
    ["Answer ［2］ and 〔3〕.", "Answer [2] and [3]."],
    ["Answer 【4†L1-L5】.", "Answer [4]."],
    ["Both 【1, 2】.", "Both [1, 2]."],
    ["Both 【1，2】.", "Both [1,2]."],
    ["Plain [1] stays.", "Plain [1] stays."],
    ["No markers.", "No markers."],
  ])("%s", (input, expected) => expect(normalizeCitationMarkers(input)).toBe(expected))
})

describe("linkifyCitations", () => {
  it("turns markers into fragment links", () => {
    expect(linkifyCitations("PTO is 20 days [1].")).toBe("PTO is 20 days [1](#cite-1).")
  })

  it("splits grouped citations into separate chips", () => {
    expect(linkifyCitations("Both agree [1, 2].")).toBe("Both agree [1](#cite-1)[2](#cite-2).")
  })

  it("leaves numbers that are not real sources as plain text", () => {
    expect(linkifyCitations("See [1] and [9].", new Set([1, 2]))).toBe("See [1](#cite-1) and [9].")
  })

  it("does not touch existing markdown links or non-numeric brackets", () => {
    expect(linkifyCitations("[1](https://x.dev) and [note]")).toBe("[1](https://x.dev) and [note]")
  })

  it("handles exotic bracket styles", () => {
    expect(linkifyCitations("Claim 【2】.")).toBe("Claim [2](#cite-2).")
  })
})

describe("citedNumbers", () => {
  it("lists each number once in order of appearance", () => {
    expect(citedNumbers("A [2]. B [1, 2]. C [3].")).toEqual([2, 1, 3])
  })

  it("is empty when nothing is cited", () => {
    expect(citedNumbers("Nothing here.")).toEqual([])
  })
})

describe("claimForCitation", () => {
  const answer = "Employees get 20 days of PTO [1]. Unused days roll over [2]. Managers approve requests [1][2]."

  it("returns only the sentences that cite the source, without markers", () => {
    expect(claimForCitation(answer, 2)).toBe("Unused days roll over. Managers approve requests.")
    expect(claimForCitation(answer, 1)).toBe("Employees get 20 days of PTO. Managers approve requests.")
  })

  it("returns an empty string for a source that is not cited", () => {
    expect(claimForCitation(answer, 7)).toBe("")
  })

  it("strips markdown emphasis and works with list items", () => {
    expect(claimForCitation("- **Gold** tier gets 4h response [3]\n- Silver gets 8h [4]", 3)).toBe(
      "- Gold tier gets 4h response",
    )
  })
})
