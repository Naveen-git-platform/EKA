export type Segment = { text: string; hit: boolean }

const STOPWORDS = new Set(
  "the and for are was were with that this from have has had not but you your all can will its into than then them they their what when where which who how why also any each per via our out may might would should could been being does did done over under about after before between".split(
    " ",
  ),
)

function words(text: string): Set<string> {
  const out = new Set<string>()
  for (const w of text.toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}_-]*/gu) ?? []) {
    if (w.length >= 3 && !STOPWORDS.has(w)) out.add(w)
  }
  return out
}

/**
 * Split `chunk` into segments and mark the sentence(s) that best match `claim` (the answer sentence that cited this
 * chunk). Concatenating the segments always reproduces `chunk` exactly. No segment is marked when nothing overlaps.
 */
export function highlightBestSentences(chunk: string, claim: string, maxHits = 2): Segment[] {
  const spans: { start: number; end: number }[] = []
  const re = /[^.!?\n]+[.!?]*\s*/g
  for (let m = re.exec(chunk); m; m = re.exec(chunk)) spans.push({ start: m.index, end: m.index + m[0].length })
  if (!spans.length) return chunk ? [{ text: chunk, hit: false }] : []

  const claimWords = words(claim)
  const scored = spans.map((s, i) => {
    const sw = words(chunk.slice(s.start, s.end))
    let shared = 0
    for (const w of sw) if (claimWords.has(w)) shared++
    // Reward covering the claim, lightly penalise very long sentences so tiny precise matches win ties.
    const score = claimWords.size ? shared / claimWords.size - Math.max(0, sw.size - 25) * 0.005 : 0
    return { i, score, shared }
  })
  const best = scored
    .filter((s) => s.shared >= 2 || (s.shared >= 1 && claimWords.size <= 3))
    .sort((a, b) => b.score - a.score || a.i - b.i)
    .slice(0, maxHits)
    .filter((s) => s.score >= scored.reduce((mx, c) => Math.max(mx, c.score), 0) * 0.5)
  const hits = new Set(best.map((s) => s.i))

  const segments: Segment[] = []
  spans.forEach((s, i) => {
    const text = chunk.slice(s.start, s.end)
    const last = segments[segments.length - 1]
    if (last && last.hit === hits.has(i)) last.text += text
    else segments.push({ text, hit: hits.has(i) })
  })
  const covered = spans[spans.length - 1].end
  if (covered < chunk.length) segments[segments.length - 1].text += chunk.slice(covered)
  return segments
}
