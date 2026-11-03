import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ensureSession, request } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());
describe("local API client", () => {
  it("creates a new private workspace only after a missing session and never submits a workspace selector", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ access_token: "not-stored", workspace_id: "own" }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            workspace_id: "own",
            mode: "offline",
            label: "Local",
            provider_status: {},
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    const session = await ensureSession();
    expect(session.workspace_id).toBe("own");
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/sessions");
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ label: "Local workspace" });
    expect(fetch.mock.calls[1][1].credentials).toBe("same-origin");
    expect(window.localStorage.length).toBe(0);
  });
  it("does not create a workspace when the local API is down", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("network"));
    vi.stubGlobal("fetch", fetch);
    await expect(ensureSession()).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("handles non-JSON proxy failures without pretending they are evidence gaps", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })),
    );
    await expect(request("/research")).rejects.toMatchObject({
      status: 502,
      message: "Request failed (502). Please try again.",
    });
  });
});
