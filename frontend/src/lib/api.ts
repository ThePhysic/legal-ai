import type {
  Dataset,
  DocumentAnalysis,
  DocumentDetail,
  EvaluationRun,
  LegalDocument,
  ResearchRequest,
  ResearchResponse,
  Session,
  Source,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(90_000);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      signal,
      headers: {
        ...(options.body && !(options.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(
      timeout.aborted
        ? "The local API took too long. Try again; no answer has been substituted."
        : "The local API could not be reached. Check that the backend is running, then try again.",
      0,
    );
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (response.status === 422)
        message =
          "The request could not be processed. Check the question, file type, or settings and try again.";
    } catch {
      /* proxy failures may not have JSON bodies */
    }
    if (response.status === 401) {
      message =
        "Your local session has expired. Reconnect to create a new private workspace.";
      if (path !== "/session" && typeof window !== "undefined")
        window.dispatchEvent(new Event("legalai:session-expired"));
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "The local API returned an unreadable response. Please try again.",
      response.status,
    );
  }
}

let sessionRequest: Promise<Session> | null = null;
export function ensureSession(): Promise<Session> {
  if (!sessionRequest) {
    sessionRequest = request<Session>("/session")
      .catch(async (error) => {
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
        await request("/sessions", {
          method: "POST",
          body: JSON.stringify({ label: "Local workspace" }),
        });
        return request<Session>("/session");
      })
      .finally(() => {
        sessionRequest = null;
      });
  }
  return sessionRequest;
}

export const api = {
  research: (body: ResearchRequest, signal?: AbortSignal) =>
    request<ResearchResponse>("/research", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  corpus: () =>
    request<{
      sources: Source[];
      coverage: string[];
      limitations: string[];
      mode: string;
    }>("/corpus"),
  trace: (id: string) =>
    request<Record<string, unknown>>(`/runs/${encodeURIComponent(id)}`),
  documents: () => request<{ documents: LegalDocument[] }>("/documents"),
  document: (id: string, signal?: AbortSignal) =>
    request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`, { signal }),
  upload: (file: File, replaceId?: string) => {
    const body = new FormData();
    body.append("file", file);
    if (replaceId) body.append("replace_document_id", replaceId);
    return request<LegalDocument>("/documents", { method: "POST", body });
  },
  retry: (id: string) =>
    request<LegalDocument>(`/documents/${encodeURIComponent(id)}/retry`, {
      method: "POST",
    }),
  deleteDocument: (id: string) =>
    request<{ document_id: string; status: "deleted" | "deletion_pending" }>(
      `/documents/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  analysis: (
    id: string,
    body: { question?: string; locator?: string },
    signal?: AbortSignal,
  ) =>
    request<DocumentAnalysis>(`/documents/${encodeURIComponent(id)}/analysis`, {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  evaluations: () =>
    request<{ runs: EvaluationRun[]; datasets: Dataset[] }>("/evaluations"),
  evaluate: (dataset_id: string, configurations: string[]) =>
    request<EvaluationRun>("/evaluations", {
      method: "POST",
      body: JSON.stringify({ dataset_id, configurations }),
    }),
  evaluation: (id: string) =>
    request<EvaluationRun>(`/evaluations/${encodeURIComponent(id)}`),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
