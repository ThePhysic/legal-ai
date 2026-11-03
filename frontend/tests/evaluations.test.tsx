import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Evaluations } from "@/components/evaluations";
import { api } from "@/lib/api";
import type { EvaluationRun } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, evaluations: vi.fn(), evaluate: vi.fn() },
  };
});

beforeEach(() => {
  vi.mocked(api.evaluations).mockReset();
  vi.mocked(api.evaluate).mockReset();
});

describe("evaluation workspace lifecycle", () => {
  it("aborts an initial private run listing when the workspace expires", () => {
    vi.mocked(api.evaluations).mockReturnValue(new Promise(() => undefined));
    const view = render(<Evaluations />);
    const signal = vi.mocked(api.evaluations).mock.calls[0][0];
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("aborts a running benchmark on workspace removal and skips its late listing refresh", async () => {
    vi.mocked(api.evaluations).mockResolvedValue({
      runs: [],
      datasets: [
        {
          id: "synthetic",
          title: "Synthetic starter",
          count: 1,
          revision: "v1",
          judgment_provenance: "Synthetic judgments",
        },
      ],
    });
    let finish!: (run: EvaluationRun) => void;
    vi.mocked(api.evaluate).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const user = userEvent.setup();
    const view = render(<Evaluations />);
    await screen.findByRole("option", { name: "Synthetic starter · 1 cases" });
    await user.click(screen.getByRole("button", { name: "Run evaluation" }));
    const signal = vi.mocked(api.evaluate).mock.calls[0][2];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () =>
      finish({
        evaluation_id: "synthetic-run",
        dataset_id: "synthetic",
        dataset_revision: "v1",
        created_at: "2026-11-03T00:00:00Z",
        status: "completed",
        method: "offline",
        judgment_provenance: "Synthetic judgments",
        configurations: [],
        limitations: [],
      }),
    );
    expect(api.evaluations).toHaveBeenCalledTimes(1);
  });
});
