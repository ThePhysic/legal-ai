import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Documents } from "@/components/documents";
import { api } from "@/lib/api";
import type { DocumentDetail, LegalDocument } from "@/lib/types";

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
beforeEach(() => {
  vi.mocked(api.documents).mockReset();
  vi.mocked(api.upload).mockReset();
  vi.mocked(api.document).mockReset();
  vi.mocked(api.deleteDocument).mockReset();
  vi.mocked(api.retry).mockReset();
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
    expect(dialog.textContent).toContain("Saved private run diagnostics");
    await user.click(within(dialog).getByRole("button", { name: "Keep document" }));
    expect(api.deleteDocument).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete document" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Delete document" }),
    );
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("doc-own"));
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
    await waitFor(() => expect(api.retry).toHaveBeenCalledWith("doc-own"));
    expect(
      await screen.findByRole("button", { name: "Read document text" }),
    ).toBeTruthy();
  });
});
