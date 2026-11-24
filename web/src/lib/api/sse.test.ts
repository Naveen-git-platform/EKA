import { describe, expect, it } from "vitest"

import { iterSse, parseSseLines, SseParser } from "@/lib/api/sse"
import { streamOf } from "@/test/utils"

const frames = (lines: string[]) => [...parseSseLines(lines)]

describe("parseSseLines", () => {
  it("parses a named frame", () => {
    expect(frames(["event: token", 'data: {"type":"token","text":"Hi"}', ""])).toEqual([
      { event: "token", data: { type: "token", text: "Hi" } },
    ])
  })

  it("falls back to the payload type when there is no event line", () => {
    expect(frames(['data: {"type":"plan","strategy":"direct"}', ""])[0].event).toBe("plan")
  })

  it("uses 'message' when neither event nor type is present", () => {
    expect(frames(['data: {"a":1}', ""])[0].event).toBe("message")
  })

  it("ignores comments / keep-alives", () => {
    expect(frames([": keep-alive", "", "event: x", 'data: {"type":"x"}', ""])).toHaveLength(1)
  })

  it("joins multi-line data", () => {
    const out = frames(["event: t", 'data: {"type":"t",', 'data: "a":1}', ""])
    expect(out[0].data).toEqual({ type: "t", a: 1 })
  })

  it("handles CRLF line endings", () => {
    expect(frames(["event: done\r", 'data: {"type":"done"}\r', "\r"])[0]).toEqual({
      event: "done",
      data: { type: "done" },
    })
  })

  it("skips frames whose data is not valid JSON or not an object", () => {
    expect(frames(["data: {broken", "", "data: [1,2]", "", "data: 5", "", "data: null", ""])).toEqual([])
  })

  it("emits a trailing frame that has no closing blank line", () => {
    expect(frames(["event: done", 'data: {"type":"done"}'])).toHaveLength(1)
  })

  it("does not carry state between frames", () => {
    const out = frames(["event: a", 'data: {"type":"a"}', "", 'data: {"type":"b"}', ""])
    expect(out.map((f) => f.event)).toEqual(["a", "b"])
  })

  it("accepts data without the optional space after the colon", () => {
    expect(frames(['data:{"type":"x"}', ""])[0].data).toEqual({ type: "x" })
  })
})

describe("SseParser", () => {
  it("returns null until a frame completes", () => {
    const p = new SseParser()
    expect(p.pushLine("event: x")).toBeNull()
    expect(p.pushLine('data: {"type":"x"}')).toBeNull()
    expect(p.pushLine("")).not.toBeNull()
    expect(p.end()).toBeNull()
  })
})

describe("iterSse", () => {
  const collect = async (chunks: string[]) => {
    const out = []
    for await (const f of iterSse(streamOf(chunks))) out.push(f)
    return out
  }

  it("reassembles frames split at arbitrary points", async () => {
    const text = 'event: token\ndata: {"type":"token","text":"Hello"}\n\nevent: done\ndata: {"type":"done"}\n\n'
    for (const cut of [1, 7, 20, 33, text.length - 2]) {
      const out = await collect([text.slice(0, cut), text.slice(cut)])
      expect(out.map((f) => f.event)).toEqual(["token", "done"])
    }
  })

  it("survives a CRLF pair split across chunks", async () => {
    const out = await collect(["event: a\r", '\ndata: {"type":"a"}\r', "\n\r", "\n"])
    expect(out).toEqual([{ event: "a", data: { type: "a" } }])
  })

  it("decodes multi-byte characters split across byte chunks", async () => {
    const bytes = new TextEncoder().encode('data: {"type":"token","text":"héllo 世界"}\n\n')
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        for (let i = 0; i < bytes.length; i += 3) c.enqueue(bytes.slice(i, i + 3))
        c.close()
      },
    })
    const out = []
    for await (const f of iterSse(stream)) out.push(f)
    expect(out[0].data.text).toBe("héllo 世界")
  })

  it("flushes a final frame without a trailing blank line", async () => {
    expect(await collect(['event: done\ndata: {"type":"done"}'])).toHaveLength(1)
  })

  it("yields nothing for an empty stream", async () => {
    expect(await collect([])).toEqual([])
  })
})
