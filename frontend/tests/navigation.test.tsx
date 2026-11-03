import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LegalApp } from "@/components/legal-app";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    ensureSession: vi.fn().mockResolvedValue({
      workspace_id: "own",
      label: "Local",
      mode: "offline",
      provider_status: {},
    }),
  };
});
vi.mock("@/components/documents", () => ({
  Documents: () => <h2>Document workspace content</h2>,
}));
vi.mock("@/components/research", () => ({
  Research: () => <h2>Research workspace content</h2>,
  EXAMPLES: ["Deposit paperwork?"],
}));
vi.mock("@/components/evaluations", () => ({
  Evaluations: () => <h2>Evaluation workspace content</h2>,
}));
vi.mock("@/components/reference", () => ({
  Reference: () => <h2>Reference workspace content</h2>,
}));

beforeEach(() => window.history.replaceState(null, "", "/"));
describe("keyboard and hash navigation", () => {
  it.each(["Research", "My documents"])(
    "skip to main preserves the %s view and focuses main",
    async (name) => {
      const user = userEvent.setup();
      render(<LegalApp />);
      await user.click(screen.getByRole("button", { name }));
      await screen.findByRole("heading", {
        name:
          name === "Research"
            ? "Research workspace content"
            : "Document workspace content",
      });
      const hash = window.location.hash;
      await user.click(screen.getByRole("link", { name: "Skip to main content" }));
      expect(document.activeElement).toBe(screen.getByRole("main"));
      expect(window.location.hash).toBe(hash);
      expect(screen.getByRole("button", { name }).getAttribute("aria-current")).toBe(
        "page",
      );
    },
  );
  it("ignores non-view hashes instead of navigating back to Home", async () => {
    const user = userEvent.setup();
    render(<LegalApp />);
    await user.click(screen.getByRole("button", { name: "My documents" }));
    await screen.findByRole("heading", { name: "Document workspace content" });
    window.location.hash = "main";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "My documents" }).getAttribute("aria-current"),
      ).toBe("page"),
    );
  });
});
