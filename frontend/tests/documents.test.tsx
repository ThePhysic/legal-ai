import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Documents } from "@/components/documents";
import { api } from "@/lib/api";
import type { DocumentAnalysis, DocumentDetail, LegalDocument } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      documents: vi.fn(),
      upload: vi.fn(),
      document: vi.fn(),
      deleteDocument: vi.fn(),
      retry: vi.fn(),
      analysis: vi.fn(),
    },
  };
});
const ready: LegalDocument = {
  document_id: "doc-own",
  filename: "own-lease.txt",
  media_type: "text/plain",
  status: "ready",
  version: "v1",
  content_hash: "hash",
  created_at: "2026-11-03T00:00:00Z",
  section_count: 1,
  passage_count: 1,
  error: null,
  processing: {},
};
const detail: DocumentDetail = {
  ...ready,
  sections: [
    { locator: "Section 1", title: "Deposit", text: "A synthetic deposit clause." },
  ],
  passages: [],
};
const other = { ...ready, document_id: "doc-other", filename: "other-lease.txt" };
const otherDetail = {
  ...detail,
  ...other,
  sections: [{ locator: "Section 2", title: "Rent", text: "Other document text." }],
};
const analysis: DocumentAnalysis = {
  document_id: ready.document_id,
  summary: "Synthetic summary",
  findings: [],
  answer: null,
  comparison: { passages: [], limitations: [] },
  method: "offline_extractive",
  limitations: [],
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
beforeEach(() => {
  vi.mocked(api.documents).mockReset();
  vi.mocked(api.upload).mockReset();
  vi.mocked(api.document).mockReset();
  vi.mocked(api.deleteDocument).mockReset();
  vi.mocked(api.retry).mockReset();
  vi.mocked(api.analysis).mockReset();
  vi.mocked(api.document).mockResolvedValue(detail);
});

describe("private document interactions", () => {
  it("submits the sample as a real File upload and opens extracted document text", async () => {
    vi.mocked(api.documents)
      .mockResolvedValueOnce({ documents: [] })
      .mockResolvedValue({ documents: [ready] });
    vi.mocked(api.upload).mockResolvedValue(ready);
    const user = userEvent.setup();
    render(<Documents />);
    await screen.findByText("A fresh workspace");
    await user.click(
      screen.getByRole("button", { name: /Try a synthetic sample lease/ }),
    );
    await screen.findByRole("button", { name: "Read document text" });
    const file = vi.mocked(api.upload).mock.calls[0][0];
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe("synthetic-sample-lease.txt");
    expect(file.size).toBeGreaterThan(100);
    await user.click(screen.getByRole("button", { name: "Read document text" }));
    expect(screen.getByText("A synthetic deposit clause.")).toBeTruthy();
  });
  it("requires confirmation and reports pending deletion without claiming completed cleanup", async () => {
    vi.mocked(api.documents)
      .mockResolvedValueOnce({ documents: [ready] })
      .mockResolvedValue({ documents: [{ ...ready, status: "deletion_pending" }] });
    vi.mocked(api.deleteDocument).mockResolvedValue({
      document_id: ready.document_id,
      status: "deletion_pending",
    });
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await screen.findByRole("button", { name: "Read document text" });
    await user.click(screen.getByRole("button", { name: "Delete document" }));
    const dialog = screen.getByRole("dialog");
    expect(api.deleteDocument).not.toHaveBeenCalled();
    expect(dialog.textContent).toContain("All saved research run history");
    expect(dialog.textContent).toContain("public sources");
    await user.click(within(dialog).getByRole("button", { name: "Keep document" }));
    expect(api.deleteDocument).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete document" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Delete document" }),
    );
    await waitFor(() =>
      expect(api.deleteDocument).toHaveBeenCalledWith("doc-own", expect.any(AbortSignal)),
    );
    expect(await screen.findByText(/Storage cleanup is still pending/)).toBeTruthy();
    expect(screen.queryByText("The API confirmed deletion of this document.")).toBeNull();
  });
  it("recovers a failed document with the real retry endpoint", async () => {
    const failed: LegalDocument = {
      ...ready,
      status: "failed",
      error: "Worker was interrupted.",
    };
    vi.mocked(api.documents)
      .mockResolvedValueOnce({ documents: [failed] })
      .mockResolvedValue({ documents: [ready] });
    vi.mocked(api.retry).mockResolvedValue(ready);
    vi.mocked(api.document)
      .mockResolvedValueOnce({ ...detail, status: "failed" })
      .mockResolvedValue(detail);
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    const retry = await screen.findByRole("button", { name: "Retry processing" });
    await waitFor(() => expect(retry.hasAttribute("disabled")).toBe(false));
    await user.click(retry);
    await waitFor(() =>
      expect(api.retry).toHaveBeenCalledWith("doc-own", expect.any(AbortSignal)),
    );
    expect(
      await screen.findByRole("button", { name: "Read document text" }),
    ).toBeTruthy();
  });
  it("opens each selection once and ignores a late aborted document response", async () => {
    const first = deferred<DocumentDetail>();
    vi.mocked(api.documents).mockResolvedValue({ documents: [ready, other] });
    vi.mocked(api.document).mockImplementation((id) =>
      id === ready.document_id ? first.promise : Promise.resolve(otherDetail),
    );
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await waitFor(() => expect(api.document).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(api.document).mock.calls[0][1];
    await user.click(screen.getByRole("button", { name: /other-lease.txt/ }));
    await user.click(await screen.findByRole("button", { name: "Read document text" }));
    expect(screen.getByText("Other document text.")).toBeTruthy();
    expect(signal?.aborted).toBe(true);
    await act(async () => first.resolve(detail));
    expect(screen.getByText("Other document text.")).toBeTruthy();
    expect(screen.queryByText("A synthetic deposit clause.")).toBeNull();
  });
  it("retries a failed detail read for the sole selected document through its error control", async () => {
    vi.mocked(api.documents).mockResolvedValue({ documents: [ready] });
    vi.mocked(api.document)
      .mockRejectedValueOnce(new Error("Document text could not be reached."))
      .mockResolvedValueOnce(detail);
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Document text could not be reached.",
    );
    expect(api.document).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    await user.click(await screen.findByRole("button", { name: "Read document text" }));
    expect(screen.getByText("A synthetic deposit clause.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(api.document).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.document).mock.calls.map(([id]) => id)).toEqual([
      ready.document_id,
      ready.document_id,
    ]);
  });
  it("cancels selection-bound retry and keeps the next document loading until its own response", async () => {
    const retry = deferred<LegalDocument>();
    const next = deferred<DocumentDetail>();
    const failed = { ...ready, status: "failed" as const };
    vi.mocked(api.documents).mockResolvedValue({ documents: [failed, other] });
    vi.mocked(api.document).mockImplementation((id) =>
      id === ready.document_id
        ? Promise.resolve({ ...detail, status: "failed" })
        : next.promise,
    );
    vi.mocked(api.retry).mockReturnValue(retry.promise);
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Retry processing" }).hasAttribute("disabled"),
      ).toBe(false),
    );
    await user.click(screen.getByRole("button", { name: "Retry processing" }));
    const signal = vi.mocked(api.retry).mock.calls[0][1];
    await user.click(screen.getByRole("button", { name: /other-lease.txt/ }));
    await act(async () => retry.reject(new Error("Late retry failure")));
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Opening document text…")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Replace file" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(api.documents).toHaveBeenCalledTimes(1);
    await act(async () => next.resolve(otherDetail));
    await user.click(await screen.findByRole("button", { name: "Read document text" }));
    expect(screen.getByText("Other document text.")).toBeTruthy();
  });
  it("does not commit cancelled analysis to another document or release its loading controls", async () => {
    const pending = deferred<DocumentAnalysis>();
    const next = deferred<DocumentDetail>();
    vi.mocked(api.documents).mockResolvedValue({ documents: [ready, other] });
    vi.mocked(api.document).mockImplementation((id) =>
      id === ready.document_id ? Promise.resolve(detail) : next.promise,
    );
    vi.mocked(api.analysis).mockReturnValue(pending.promise);
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await user.click(
      await screen.findByRole("button", { name: "Analyze & compare sources" }),
    );
    await user.click(screen.getByRole("button", { name: /other-lease.txt/ }));
    await act(async () => pending.resolve(analysis));
    expect(vi.mocked(api.analysis).mock.calls[0][2]?.aborted).toBe(true);
    expect(screen.queryByText("Synthetic summary")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Replace file" }).hasAttribute("disabled"),
    ).toBe(true);
    await act(async () => next.resolve(otherDetail));
    expect(
      await screen.findByRole("button", { name: "Analyze & compare sources" }),
    ).toBeTruthy();
  });
  it("keeps the newer document listing when refresh responses finish out of order", async () => {
    const earlier = deferred<{ documents: LegalDocument[] }>();
    const later = deferred<{ documents: LegalDocument[] }>();
    vi.mocked(api.documents)
      .mockResolvedValueOnce({ documents: [ready] })
      .mockReturnValueOnce(earlier.promise)
      .mockReturnValueOnce(later.promise);
    const user = userEvent.setup();
    render(<Documents />);
    await screen.findByRole("button", { name: /own-lease.txt/ });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await act(async () => later.resolve({ documents: [other] }));
    await act(async () => earlier.resolve({ documents: [ready] }));
    expect(screen.getByRole("button", { name: /other-lease.txt/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /own-lease.txt/ })).toBeNull();
  });
  it("aborts an upload when its workspace unmounts and skips later follow-up requests", async () => {
    const pending = deferred<LegalDocument>();
    vi.mocked(api.documents).mockResolvedValue({ documents: [] });
    vi.mocked(api.upload).mockReturnValue(pending.promise);
    const user = userEvent.setup();
    const view = render(<Documents />);
    await screen.findByText("A fresh workspace");
    await user.click(
      screen.getByRole("button", { name: /Try a synthetic sample lease/ }),
    );
    const signal = vi.mocked(api.upload).mock.calls[0][2];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => pending.resolve(ready));
    expect(api.documents).toHaveBeenCalledTimes(1);
    expect(api.document).not.toHaveBeenCalled();
  });
  it("keeps an already selected ready document open after an identical upload", async () => {
    vi.mocked(api.documents).mockResolvedValue({ documents: [ready] });
    vi.mocked(api.upload).mockResolvedValue(ready);
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await user.click(await screen.findByRole("button", { name: "Read document text" }));
    await user.click(
      screen.getByRole("button", { name: /Try a synthetic sample lease/ }),
    );
    expect(await screen.findByText("A synthetic deposit clause.")).toBeTruthy();
    expect(api.document).toHaveBeenCalledTimes(1);
  });
  it("describes a literal section fact without falsely claiming passage validation", async () => {
    vi.mocked(api.documents).mockResolvedValue({ documents: [ready] });
    vi.mocked(api.analysis).mockResolvedValue({
      ...analysis,
      findings: [
        {
          kind: "document_fact",
          title: "Deposit",
          text: "Literal section fact",
          locator: "Section 1",
          passage_ids: [],
          verified: false,
        },
      ],
    });
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await user.click(
      await screen.findByRole("button", { name: "Analyze & compare sources" }),
    );
    expect(
      await screen.findByText(/Exact section text; passage match not established/),
    ).toBeTruthy();
    expect(screen.queryByText(/Rule-based consideration;/)).toBeNull();
    await user.click(screen.getByRole("button", { name: /Read the document text/ }));
    expect(screen.getByText("A synthetic deposit clause.")).toBeTruthy();
  });
  it("keeps a confirmed deletion visible when the subsequent listing refresh fails", async () => {
    const pending = deferred<{ documents: LegalDocument[] }>();
    vi.mocked(api.documents)
      .mockResolvedValueOnce({ documents: [ready] })
      .mockReturnValueOnce(pending.promise);
    vi.mocked(api.deleteDocument).mockResolvedValue({
      document_id: ready.document_id,
      status: "deleted",
    });
    const user = userEvent.setup();
    render(<Documents />);
    await user.click(await screen.findByRole("button", { name: /own-lease.txt/ }));
    await screen.findByRole("button", { name: "Read document text" });
    await user.click(screen.getByRole("button", { name: "Delete document" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Delete document" }),
    );
    expect(
      await screen.findByText("The API confirmed deletion of this document."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /own-lease.txt/ })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Upload document" }).hasAttribute("disabled"),
    ).toBe(true);
    await act(async () => pending.reject(new Error("Listing refresh failed")));
    expect(screen.getByText("The API confirmed deletion of this document.")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Listing refresh failed");
    expect(
      screen.getByRole("button", { name: "Upload document" }).hasAttribute("disabled"),
    ).toBe(false);
  });
});
