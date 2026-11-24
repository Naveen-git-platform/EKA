import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { SourceDrawer } from "@/components/chat/source-drawer"
import { source } from "@/test/fixtures"

const sources = [
  source(1, {
    filename: "handbook.md",
    page: 3,
    text: "Intro line. Full-time employees receive 20 days of PTO per year. Closing line.",
  }),
  source(2, { filename: "faq.txt", text: "Unrelated text only." }),
]
const answer = "Employees receive 20 days of PTO per year [1]."

const setup = (openIndex: number | null, onChange = vi.fn()) => {
  render(
    <SourceDrawer sources={sources} cited={[1]} answer={answer} openIndex={openIndex} onOpenIndexChange={onChange} />,
  )
  return onChange
}

describe("SourceDrawer", () => {
  it("renders nothing while closed", () => {
    setup(null)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("shows the source's file, page and cited state", () => {
    setup(1)
    expect(screen.getByRole("dialog")).toHaveTextContent("handbook.md")
    expect(screen.getByText("Page 3")).toBeInTheDocument()
    expect(screen.getByText("Cited in answer")).toBeInTheDocument()
  })

  it("shows the claim and highlights the best matching sentence", () => {
    setup(1)
    expect(screen.getByText("The answer says").nextSibling).toHaveTextContent(
      "Employees receive 20 days of PTO per year.",
    )
    const mark = screen.getByTestId("source-text").querySelector("mark")
    expect(mark).toHaveTextContent("Full-time employees receive 20 days of PTO per year.")
  })

  it("keeps the full source text readable around the highlight", () => {
    setup(1)
    expect(screen.getByTestId("source-text")).toHaveTextContent(sources[0].text)
  })

  it("labels sources that were retrieved but not cited and highlights nothing", () => {
    setup(2)
    expect(screen.getByText("Retrieved, not cited")).toBeInTheDocument()
    expect(screen.getByTestId("source-text").querySelector("mark")).toBeNull()
  })

  it("navigates between sources", async () => {
    const onChange = setup(1)
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled()
    await userEvent.click(screen.getByRole("button", { name: /next/i }))
    expect(onChange).toHaveBeenCalledWith(2)
    expect(screen.getByText("1 of 2")).toBeInTheDocument()
  })

  it("disables Next on the last source", () => {
    setup(2)
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled()
  })

  it("asks to close when dismissed", async () => {
    const onChange = setup(1)
    await userEvent.keyboard("{Escape}")
    expect(onChange).toHaveBeenCalledWith(null)
  })
})
