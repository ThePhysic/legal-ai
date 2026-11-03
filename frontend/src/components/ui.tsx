"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Passage, ResearchResponse } from "@/lib/types";

export function Icon({
  name,
  size = 20,
}: {
  name:
    | "search"
    | "file"
    | "arrow"
    | "home"
    | "chart"
    | "book"
    | "shield"
    | "plus"
    | "close"
    | "check";
  size?: number;
}) {
  const paths = {
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    file: (
      <>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h4M9 12h6M9 16h6" />
      </>
    ),
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    home: <path d="m3 10 9-7 9 7M6 9v12h12V9M10 21v-7h4v7" />,
    chart: <path d="M4 3v18h17M8 16v-5m5 5V6m5 10V9" />,
    book: <path d="M12 5v16M3 4c4-1 7 0 9 2 2-2 5-3 9-2v15c-4-1-7 0-9 2-2-2-5-3-9-2z" />,
    shield: <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6" />,
    plus: <path d="M12 4v16M4 12h16" />,
    close: <path d="m5 5 14 14M5 19 19 5" />,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "green" | "gold" | "red";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function ErrorNotice({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <strong>We couldn’t complete that request.</strong>
      <p>{message}</p>
      {onRetry && (
        <button className="text-button" onClick={onRetry}>
          Try again ↗
        </button>
      )}
    </div>
  );
}
export function Busy({ children }: { children: React.ReactNode }) {
  return (
    <p className="busy" role="status">
      <span className="spinner" aria-hidden="true" />
      {children}
    </p>
  );
}
export function EmptyState({
  title,
  children,
  icon = "file",
}: {
  title: string;
  children: React.ReactNode;
  icon?: "file" | "search" | "chart";
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name={icon} size={28} />
      </span>
      <h3>{title}</h3>
      <div className="muted">{children}</div>
    </div>
  );
}
export function dateLabel(value: string | null | undefined) {
  if (!value) return "Unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      });
}

export function PassageInspector({
  passages,
  selected,
  onSelect,
  title = "Inspect the sources",
}: {
  passages: Passage[];
  selected: string | null;
  onSelect: (id: string) => void;
  title?: string;
}) {
  const passage = passages.find((p) => p.passage_id === selected) ?? passages[0];
  const source = passage?.source;
  const excerpt = useRef<HTMLQuoteElement>(null);
  function selectPassage(id: string) {
    onSelect(id);
    window.requestAnimationFrame(() => {
      excerpt.current?.focus();
      excerpt.current?.scrollIntoView({ behavior: "auto", block: "nearest" });
    });
  }
  const count = new Set(passages.map((p) => p.source_id)).size;
  return (
    <aside className="card source-inspector" aria-label={title}>
      <div className="panel-heading">
        <span className="eyebrow">Evidence, in context</span>
        <h2>{title}</h2>
        <p className="muted">
          {passages.length} retrieved {passages.length === 1 ? "passage" : "passages"} ·{" "}
          {count} archived {count === 1 ? "source" : "sources"}
        </p>
      </div>
      {passages.length > 0 && (
        <>
          <div className="passage-tabs" aria-label="Choose a passage">
            {passages.map((p, i) => (
              <button
                type="button"
                key={p.passage_id}
                aria-pressed={passage?.passage_id === p.passage_id}
                onClick={() => selectPassage(p.passage_id)}
                className="passage-tab"
              >
                <span className="cite-number">{String(i + 1).padStart(2, "0")}</span>
                <span>{p.locator || p.source.title}</span>
              </button>
            ))}
          </div>
          {passage && source && (
            <div className="source-body">
              <p className="sr-only" role="status" aria-live="polite">
                Showing {source.title}, {passage.locator}, passage{" "}
                {passages.findIndex((p) => p.passage_id === passage.passage_id) + 1} of{" "}
                {passages.length}.
              </p>
              <div className="row wrap">
                <Badge tone={source.scope === "private" ? "gold" : "green"}>
                  {source.scope === "private" ? "Private document" : "Public authority"}
                </Badge>
                <span className="small muted">{source.jurisdiction}</span>
              </div>
              <h3>{source.title}</h3>
              <p className="small muted">
                {source.publisher} · {passage.locator}
              </p>
              <blockquote
                ref={excerpt}
                data-source-excerpt
                tabIndex={0}
                aria-label="Source passage text"
              >
                {passage.text}
              </blockquote>
              <div className="source-dates">
                <div>
                  <span>Captured</span>
                  <strong>{dateLabel(source.captured_at)}</strong>
                </div>
                <div>
                  <span>Effective from</span>
                  <strong>{dateLabel(source.effective_from)}</strong>
                </div>
                <div>
                  <span>Effective through</span>
                  <strong>{dateLabel(source.effective_to)}</strong>
                </div>
              </div>
              <p className="small muted">
                A capture date records when text was saved. It does not establish which
                version applies to your situation.
              </p>
              {source.url && /^https?:\/\//i.test(source.url) && (
                <a
                  className="source-link"
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Visit original source ↗
                </a>
              )}
              <details className="advanced">
                <summary>About this source &amp; passage</summary>
                <dl className="metadata">
                  <dt>Source ID</dt>
                  <dd>{source.source_id}</dd>
                  <dt>Passage ID</dt>
                  <dd>{passage.passage_id}</dd>
                  <dt>Version</dt>
                  <dd>{passage.version}</dd>
                  <dt>Content hash</dt>
                  <dd>{source.content_hash}</dd>
                  <dt>Rights basis</dt>
                  <dd>{source.rights_basis}</dd>
                  <dt>Retrieval score</dt>
                  <dd>
                    {Number.isFinite(passage.score)
                      ? passage.score.toFixed(4)
                      : "Not supplied"}{" "}
                    (not a correctness probability)
                  </dd>
                </dl>
              </details>
            </div>
          )}
        </>
      )}
      {!passage && (
        <EmptyState title="No passages returned" icon="search">
          <p>No archived passage is available to inspect.</p>
        </EmptyState>
      )}
    </aside>
  );
}

export function ResearchAnswer({
  result,
  title = "Your answer",
}: {
  result: ResearchResponse;
  title?: string;
}) {
  const [selected, setSelected] = useState<string | null>(
    result.passages[0]?.passage_id ?? null,
  );
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [traceError, setTraceError] = useState("");
  const [traceBusy, setTraceBusy] = useState(false);
  const traceAbort = useRef<AbortController | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    setSelected(result.passages[0]?.passage_id ?? null);
    setTrace(null);
    setTraceError("");
    setTraceBusy(false);
    if (!resultHeading.current?.closest("[hidden]")) {
      resultHeading.current?.focus({ preventScroll: true });
      resultHeading.current
        ?.closest(".answer-card")
        ?.scrollIntoView({ behavior: "auto", block: "start" });
    }
    return () => traceAbort.current?.abort();
  }, [result]);
  const supportedIds = new Set(result.claims.flatMap((c) => c.passage_ids));
  const supporting = result.passages.filter((p) => supportedIds.has(p.passage_id));
  const limits = [...new Set([...result.coverage_gaps, ...result.limitations])];
  const firstExtract =
    result.claims[0]?.text || result.passages[0]?.text || result.answer;
  const firstSentence =
    [
      ...new Intl.Segmenter("en", { granularity: "sentence" }).segment(firstExtract),
    ][0]?.segment.trim() || firstExtract;
  const takeaway =
    firstSentence.length <= 360
      ? firstSentence
      : `${firstSentence.slice(0, 360).replace(/\s+\S*$/, "")}…`;
  async function loadTrace() {
    const controller = new AbortController();
    traceAbort.current?.abort();
    traceAbort.current = controller;
    setTraceBusy(true);
    setTraceError("");
    try {
      const data = await api.trace(result.run_id, controller.signal);
      if (!controller.signal.aborted) setTrace(data);
    } catch (e) {
      if (!controller.signal.aborted) setTraceError(errorMessage(e));
    } finally {
      if (!controller.signal.aborted) setTraceBusy(false);
    }
  }
  return (
    <div className="answer-grid">
      <section className="card answer-card" aria-label={title}>
        <div className="row spread wrap">
          <span className="eyebrow">{title}</span>
          <Badge
            tone={
              result.status === "answered"
                ? "green"
                : result.status === "unavailable"
                  ? "red"
                  : "gold"
            }
          >
            {result.status === "answered"
              ? "Source-linked extraction"
              : result.status === "unavailable"
                ? "Service unavailable"
                : "Insufficient evidence"}
          </Badge>
        </div>
        <h2 ref={resultHeading} tabIndex={-1} className="answer-title">
          {result.status === "answered"
            ? "An excerpt to start with"
            : result.status === "unavailable"
              ? "The service could not produce an answer."
              : "The available evidence does not answer this."}
        </h2>
        {result.status === "answered" && (
          <p className="small muted takeaway-label">
            First retrieved extract · not a complete answer. Read the full supporting text
            below.
          </p>
        )}
        <p className="answer-text">
          {result.status === "answered" ? takeaway : result.answer}
        </p>
        {result.status === "unavailable" && (
          <p className="notice">
            This is a service failure, not a finding that legal evidence is unavailable.
            Retry when the service is ready.
          </p>
        )}
        <div className="answer-section">
          <h3>What the sources support</h3>
          {result.claims.length ? (
            <div className="claim-list">
              {result.claims.map((claim) => (
                <div key={claim.claim_id} className="claim">
                  <p>{claim.text}</p>
                  <div className="row wrap">
                    {claim.passage_ids.map((id) => {
                      const i = result.passages.findIndex((p) => p.passage_id === id);
                      return i >= 0 ? (
                        <button
                          className="citation"
                          key={id}
                          onClick={() => {
                            setSelected(id);
                            window.requestAnimationFrame(() => {
                              const excerpt = document
                                .getElementById(`evidence-${result.run_id}`)
                                ?.querySelector<HTMLElement>("[data-source-excerpt]");
                              excerpt?.focus();
                              excerpt?.scrollIntoView({
                                behavior: "auto",
                                block: "nearest",
                              });
                            });
                          }}
                          aria-label={`Read supporting passage ${i + 1}`}
                          aria-pressed={selected === id}
                        >
                          {String(i + 1).padStart(2, "0")}
                        </button>
                      ) : null;
                    })}
                    <span className="small muted">
                      {claim.support_status === "verbatim_quote"
                        ? "Verbatim source text"
                        : "Semantic support not assessed"}{" "}
                      ·{" "}
                      {claim.identity_validated
                        ? "Citation identity checked"
                        : "Citation identity not validated"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No supported claims were returned.</p>
          )}
          <p className="small muted support-caption">
            {supporting.length} supporting{" "}
            {supporting.length === 1 ? "passage" : "passages"}. A source link alone is not
            supporting evidence. Citation identity is separate from semantic verification.
          </p>
        </div>
        <div className="answer-section">
          <h3>What still needs checking</h3>
          {limits.length > 0 ? (
            <ul className="limits-list">
              {limits.map((limit, i) => (
                <li key={i}>{limit}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              The response does not establish applicability to an individual situation.
            </p>
          )}
          <p className="small muted">
            This is an explanation of retrieved text, not a legal determination.
            Individual facts, local rules, and applicable dates may require professional
            review.
          </p>
        </div>
        <details className="advanced">
          <summary>Method, configuration &amp; run details</summary>
          <dl className="metadata">
            <dt>Execution method</dt>
            <dd>{result.method}</dd>
            <dt>Retrieval configuration</dt>
            <dd>{result.configuration}</dd>
            <dt>Run ID</dt>
            <dd>{result.run_id}</dd>
            <dt>Semantic support</dt>
            <dd>Not independently assessed</dd>
          </dl>
          <p className="small muted">
            Offline extraction and the deterministic local vector baseline do not call an
            AI model or Pinecone.
          </p>
          <details>
            <summary>Raw extractive response</summary>
            <pre aria-label="Raw extractive answer">{result.answer}</pre>
          </details>
          <pre>{JSON.stringify(result.usage, null, 2)}</pre>
          <button className="secondary" onClick={loadTrace} disabled={traceBusy}>
            {traceBusy ? "Loading run…" : "Inspect saved run"}
          </button>
          {traceError && <ErrorNotice message={traceError} onRetry={loadTrace} />}
          {trace && (
            <pre aria-label="Saved run details">{JSON.stringify(trace, null, 2)}</pre>
          )}
        </details>
      </section>
      <div id={`evidence-${result.run_id}`}>
        <PassageInspector
          passages={result.passages}
          selected={selected}
          onSelect={setSelected}
        />
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      aria-labelledby="dialog-title"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const buttons = [
          ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
            "button:not(:disabled)",
          ),
        ];
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (!first) {
          event.preventDefault();
          return;
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <h2 id="dialog-title">{title}</h2>
      <div className="dialog-body">{children}</div>
      <div className="row dialog-actions">
        <button className="secondary" autoFocus disabled={busy} onClick={onClose}>
          Keep document
        </button>
        <button className="danger" disabled={busy} onClick={onConfirm}>
          {busy ? "Deleting…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
