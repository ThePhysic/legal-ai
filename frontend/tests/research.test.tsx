import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Research } from "@/components/research";
import { ResearchAnswer } from "@/components/ui";
import { api } from "@/lib/api";
import type { ResearchResponse } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, research: vi.fn(), trace: vi.fn() } };
});
const result: ResearchResponse = {
  run_id: "run-test",
  status: "answered",
  question: "What paperwork?",
  answer: "An itemized statement is described in the source.",
  claims: [
    {
      claim_id: "c1",
      text: "An itemized statement.",
      passage_ids: ["p1"],
      source_ids: ["s1"],
      support_status: "verbatim_quote",
      identity_validated: true,
    },
  ],
  passages: [
    {
      passage_id: "p1",
      source_id: "s1",
      version: "v1",
      locator: "1950.5 / page 1",
      text: "An itemized statement.",
      score: 2,
      source: {
        source_id: "s1",
        title: "Captured statute",
        publisher: "State",
        url: "https://example.org/statute",
        source_type: "statute",
        jurisdiction: "US-CA",
        version: "v1",
        content_hash: "hash",
        captured_at: "2026-11-03T00:00:00Z",
        effective_from: null,
        effective_to: null,
        rights_basis: "Government edict",
        scope: "public",
      },
    },
  ],
  coverage_gaps: [],
  limitations: ["Effective dates are unknown."],
  method: "offline_extractive",
  configuration: "lexical",
  usage: {},
};

beforeEach(() => {
  vi.mocked(api.research).mockReset();
  vi.mocked(api.trace).mockReset();
});
describe("research interactions", () => {
  it("sends the customer's free-form question and displays actual returned passages", async () => {
    vi.mocked(api.research).mockResolvedValue(result);
    const user = userEvent.setup();
    render(<Research initialQuestion="" onQuestionConsumed={() => undefined} />);
    await user.type(
      screen.getByLabelText("What would you like to understand?"),
      "Which paperwork explains deposit deductions?",
    );
    await user.click(screen.getByRole("button", { name: "Search legal sources" }));
    await screen.findByRole("heading", { name: "An excerpt to start with" });
    expect(api.research).toHaveBeenCalledWith(
      expect.objectContaining({
        question: "Which paperwork explains deposit deductions?",
        source_scope: "public",
        applicable_on: null,
      }),
      expect.any(AbortSignal),
    );
    expect(screen.getByText(/1 supporting passage\./).textContent).toContain(
      "A source link alone is not supporting evidence",
    );
    expect(screen.getByLabelText("Source passage text").textContent).toBe(
      "An itemized statement.",
    );
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
    expect(screen.getByText(/Citation identity checked/)).toBeTruthy();
  });
  it("distinguishes a network/provider error from insufficient evidence and offers retry", async () => {
    vi.mocked(api.research).mockRejectedValue(
      new Error("The local API could not be reached."),
    );
    const user = userEvent.setup();
    render(<Research initialQuestion="" onQuestionConsumed={() => undefined} />);
    fireEvent.change(screen.getByLabelText("What would you like to understand?"), {
      target: { value: "Where are the sources?" },
    });
    await user.click(screen.getByRole("button", { name: "Search legal sources" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "could not be reached",
    );
    expect(screen.queryByText("Insufficient evidence")).toBeNull();
    vi.mocked(api.research).mockResolvedValue({
      ...result,
      status: "insufficient_evidence",
      answer: "The source dates are unknown.",
      claims: [],
      passages: [],
    });
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByText("Insufficient evidence")).toBeTruthy();
    expect(screen.getByText("No supported claims were returned.")).toBeTruthy();
  });
  it("does not show source-free claims as supporting passages", () => {
    render(<ResearchAnswer result={{ ...result, claims: [], passages: [] }} />);
    expect(screen.getByText(/0 supporting passages\./)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Read supporting passage 1" }),
    ).toBeNull();
  });
  it("moves keyboard focus from a citation to its exact source passage", async () => {
    const user = userEvent.setup();
    render(<ResearchAnswer result={result} />);
    await user.click(screen.getByRole("button", { name: "Read supporting passage 1" }));
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByLabelText("Source passage text")),
    );
    expect(screen.getByRole("status").textContent).toContain(
      "Showing Captured statute, 1950.5 / page 1",
    );
  });
  it("uses a concise exact extract before full support and keeps the raw API response in advanced details", () => {
    const firstSentence = "The source begins with this complete sentence.";
    const claim = `${firstSentence} ${"Additional source text. ".repeat(25)}`;
    render(
      <ResearchAnswer
        result={{
          ...result,
          answer: `${claim}\nAnother long joined passage.`,
          claims: [{ ...result.claims[0], text: claim }],
        }}
      />,
    );
    const answer = screen.getByRole("region", { name: "Your answer" });
    expect(answer.querySelector(".answer-text")?.textContent).toBe(firstSentence);
    expect(answer.querySelector(".claim p")?.textContent).toBe(claim);
    expect(screen.getByLabelText("Raw extractive answer").textContent).toContain(
      "Another long joined passage.",
    );
    expect(
      screen.getByText(/First retrieved extract · not a complete answer/),
    ).toBeTruthy();
  });
  it("lets a customer cancel a pending local request", async () => {
    let observed: AbortSignal | undefined;
    vi.mocked(api.research).mockImplementation((_body, signal) => {
      observed = signal;
      return new Promise((_resolve, reject) =>
        signal?.addEventListener("abort", () =>
          reject(new DOMException("Cancelled", "AbortError")),
        ),
      );
    });
    const user = userEvent.setup();
    render(<Research initialQuestion="" onQuestionConsumed={() => undefined} />);
    fireEvent.change(screen.getByLabelText("What would you like to understand?"), {
      target: { value: "Deposit paperwork" },
    });
    await user.click(screen.getByRole("button", { name: "Search legal sources" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(observed?.aborted).toBe(true));
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("ignores a cancelled response that arrives after the next research answer", async () => {
    let finish!: (value: ResearchResponse) => void;
    vi.mocked(api.research)
      .mockReturnValueOnce(
        new Promise<ResearchResponse>((resolve) => {
          finish = resolve;
        }),
      )
      .mockResolvedValueOnce({
        ...result,
        run_id: "new-run",
        claims: [{ ...result.claims[0], text: "Current question evidence." }],
      });
    const user = userEvent.setup();
    render(
      <Research
        initialQuestion="Deposit paperwork?"
        onQuestionConsumed={() => undefined}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Search legal sources" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Search legal sources" }));
    await screen.findByRole("heading", { name: "An excerpt to start with" });
    await act(async () => finish(result));
    expect(
      screen.getByRole("region", { name: "Your answer" }).querySelector(".answer-text")
        ?.textContent,
    ).toBe("Current question evidence.");
  });
  it("clears and cancels saved trace details when a document answer changes", async () => {
    let finish!: (value: Record<string, unknown>) => void;
    vi.mocked(api.trace).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const user = userEvent.setup();
    const view = render(<ResearchAnswer result={result} />);
    await user.click(screen.getByText("Method, configuration & run details"));
    await user.click(screen.getByRole("button", { name: "Inspect saved run" }));
    const signal = vi.mocked(api.trace).mock.calls[0][1];
    view.rerender(<ResearchAnswer result={{ ...result, run_id: "next-run" }} />);
    expect(signal?.aborted).toBe(true);
    await act(async () =>
      finish({ run_id: "run-test", text: "Previous private answer" }),
    );
    expect(screen.queryByLabelText("Saved run details")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Inspect saved run" }).hasAttribute("disabled"),
    ).toBe(false);
  });
});
