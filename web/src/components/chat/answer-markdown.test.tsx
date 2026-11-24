import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AnswerMarkdown } from "@/components/chat/answer-markdown"
import { source } from "@/test/fixtures"

const sources = [source(1, { filename: "handbook.md" }), source(2, { filename: "faq.txt" })]

describe("AnswerMarkdown", () => {
  it("renders markdown formatting", () => {
    render(<AnswerMarkdown text={"**Bold** claim\n\n- one\n- two"} sources={[]} />)
    expect(screen.getByText("Bold").tagName).toBe("STRONG")
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
  })

  it("turns [n] into clickable chips that report the source number", async () => {
    const onCite = vi.fn()
    render(<AnswerMarkdown text="PTO is 20 days [1]. Rollover is 5 days [2]." sources={sources} onCite={onCite} />)
    const chip = screen.getByRole("button", { name: "Source 2: faq.txt" })
    expect(chip).toHaveTextContent("2")
    await userEvent.click(chip)
    expect(onCite).toHaveBeenCalledWith(2)
  })

  it("splits grouped citations into separate chips", () => {
    render(<AnswerMarkdown text="Both agree [1, 2]." sources={sources} onCite={() => {}} />)
    expect(screen.getAllByRole("button")).toHaveLength(2)
  })

  it("leaves numbers that are not sources as plain text", () => {
    render(<AnswerMarkdown text="Value is [9]." sources={sources} onCite={() => {}} />)
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.getByText("Value is [9].")).toBeInTheDocument()
  })

  it("normalises 【n】 markers while the answer is still streaming", () => {
    render(<AnswerMarkdown text="Claim 【1】." sources={sources} onCite={() => {}} />)
    expect(screen.getByRole("button", { name: /Source 1/ })).toBeInTheDocument()
  })

  it("shows inert chips before the sources have arrived", () => {
    render(<AnswerMarkdown text="Claim [1]." sources={[]} />)
    expect(screen.getByRole("button", { name: "Source 1" })).toBeDisabled()
  })

  it("opens real links in a new tab safely", () => {
    render(<AnswerMarkdown text="See [the docs](https://example.com)." sources={[]} />)
    const link = screen.getByRole("link", { name: "the docs" })
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("does not render raw HTML from the model", () => {
    render(<AnswerMarkdown text={'<img src=x onerror="alert(1)"> hi'} sources={[]} />)
    expect(document.querySelector("img")).toBeNull()
  })

  it("does not create javascript: links", () => {
    render(<AnswerMarkdown text="[click](javascript:alert(1))" sources={[]} />)
    const a = document.querySelector("a")
    expect(a?.getAttribute("href") ?? "").not.toMatch(/^javascript:/i)
  })
})
