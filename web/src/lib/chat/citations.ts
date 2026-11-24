/**
 * Citation helpers. Models cite sources as [1], but some write 【1】 or 【4†L1-L5】; this mirrors the backend's
 * normalisation so text that is still streaming looks right before the final, cleaned answer arrives.
 */
const DAGGER = /[【［〔]\s*(\d+)\s*†[^】］〕\n]*[】］〕]/g
const ALT = /[【［〔]\s*(\d+(?:\s*[,;，]\s*\d+)*)\s*[】］〕]/g
const MARKER = /\[(\d+(?:\s*[,;]\s*\d+)*)\](?!\()/g

export function normalizeCitationMarkers(text: string): string {
  return text.replace(DAGGER, (_, n) => `[${n}]`).replace(ALT, (_, nums: string) => `[${nums.replace("，", ",")}]`)
}

const parseNumbers = (group: string) => group.split(/[,;]/).map((n) => Number(n.trim()))

/**
 * Turn `[1]` / `[1, 2]` into markdown links (`[1](#cite-1)`) the renderer swaps for clickable chips.
 * Numbers that are not real sources (when `valid` is given) are left alone as plain text.
 */
export function linkifyCitations(text: string, valid?: ReadonlySet<number>): string {
  return normalizeCitationMarkers(text).replace(MARKER, (whole, group: string) => {
    const nums = parseNumbers(group)
    if (valid && !nums.every((n) => valid.has(n))) return whole
    return nums.map((n) => `[${n}](#cite-${n})`).join("")
  })
}

/** All source numbers cited anywhere in the text, in order of first appearance. */
export function citedNumbers(text: string): number[] {
  const seen: number[] = []
  for (const m of normalizeCitationMarkers(text).matchAll(MARKER)) {
    for (const n of parseNumbers(m[1])) if (!seen.includes(n)) seen.push(n)
  }
  return seen
}

/** The sentence(s) of the answer that cite source `n`, without citation markers - the "claim" the source supports. */
export function claimForCitation(answer: string, n: number): string {
  const text = normalizeCitationMarkers(answer)
  const sentences = text.split(/(?<=[.!?])\s+|\n+/)
  const claims = sentences.filter((s) => [...s.matchAll(MARKER)].some((m) => parseNumbers(m[1]).includes(n)))
  return claims
    .join(" ")
    .replace(MARKER, "")
    .replace(/[*_`#>]/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim()
}
