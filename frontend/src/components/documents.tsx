"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, isAbort } from "@/lib/api";
import { SAMPLE_LEASE } from "@/lib/sample";
import type { DocumentAnalysis, DocumentDetail, LegalDocument } from "@/lib/types";
import {
  Badge,
  Busy,
  ConfirmDialog,
  dateLabel,
  EmptyState,
  ErrorNotice,
  Icon,
  PassageInspector,
  ResearchAnswer,
} from "./ui";

const STATUS_LABELS: Record<LegalDocument["status"], string> = {
  uploaded: "Uploaded",
  extracting: "Extracting text",
  chunking: "Preparing sections",
  indexing: "Preparing for questions",
  verifying: "Checking passages",
  ready: "Ready",
  failed: "Needs attention",
  deleted: "Deleted",
  deletion_pending: "Deletion pending",
};
const ACTIVE = [
  "uploaded",
  "extracting",
  "chunking",
  "indexing",
  "verifying",
  "deletion_pending",
];

export function Documents() {
  const [documents, setDocuments] = useState<LegalDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadedDetail, setDetail] = useState<DocumentDetail | null>(null);
  const detail = loadedDetail?.document_id === selectedId ? loadedDetail : null;
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [operation, setOperation] = useState<"upload" | "analysis" | "retry" | "">("");
  const [listBusy, setListBusy] = useState(true);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailRevision, setDetailRevision] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [question, setQuestion] = useState("");
  const [locator, setLocator] = useState("");
  const [compareId, setCompareId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const busy = deleting
    ? "delete"
    : operation || (detailBusy ? "detail" : listBusy ? "list" : "");
  const [replacement, setReplacement] = useState(false);
  const [tab, setTab] = useState<"points" | "text">("points");
  const input = useRef<HTMLInputElement>(null);
  const listHeading = useRef<HTMLHeadingElement>(null);
  const analysisHeading = useRef<HTMLHeadingElement>(null);
  const analysisAbort = useRef<AbortController | null>(null);
  const detailAbort = useRef<AbortController | null>(null);
  const operationAbort = useRef<AbortController | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  const refreshSequence = useRef(0);
  const selectionRef = useRef<string | null>(null);
  const selected = documents.find((d) => d.document_id === selectedId) ?? null;
  const refresh = useCallback(async (signal = lifetime.current!.signal) => {
    const sequence = ++refreshSequence.current;
    const data = await api.documents(signal);
    if (!signal.aborted && sequence === refreshSequence.current)
      setDocuments(data.documents.filter((d) => d.status !== "deleted"));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    refresh(controller.signal)
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setListBusy(false);
      });
    return () => {
      controller.abort();
      operationAbort.current?.abort();
      analysisAbort.current?.abort();
    };
  }, [refresh]);
  useEffect(() => {
    if (!documents.some((d) => ACTIVE.includes(d.status))) return;
    const id = setInterval(() => {
      const signal = lifetime.current!.signal;
      void refresh(signal).catch((e) => {
        if (!signal.aborted) setError(errorMessage(e));
      });
    }, 1800);
    return () => clearInterval(id);
  }, [documents, refresh]);
  useEffect(() => {
    if (!selectedId || !selected) {
      setDetailBusy(false);
      return;
    }
    const abort = new AbortController();
    detailAbort.current = abort;
    setDetailBusy(true);
    setDetailError("");
    api
      .document(selectedId, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted && selectionRef.current === selectedId) setDetail(data);
      })
      .catch((e) => {
        if (!abort.signal.aborted && !isAbort(e)) setDetailError(errorMessage(e));
      })
      .finally(() => {
        if (!abort.signal.aborted) setDetailBusy(false);
      });
    return () => abort.abort();
  }, [selectedId, selected?.status, detailRevision]);
  useEffect(() => {
    if (analysis && !analysis.answer && !analysisHeading.current?.closest("[hidden]")) {
      analysisHeading.current?.focus({ preventScroll: true });
      analysisHeading.current?.scrollIntoView({ behavior: "auto", block: "start" });
    }
  }, [analysis]);
  useEffect(() => {
    if (tab === "text" && locator && detail) {
      const index = detail.sections.findIndex((section) => section.locator === locator);
      const element = document.getElementById(`section-${index}`);
      if (!element?.closest("[hidden]")) {
        element?.focus();
        element?.scrollIntoView({ behavior: "auto", block: "nearest" });
      }
    }
  }, [tab, locator, detail]);
  function chooseDocument(id: string | null) {
    if (selectionRef.current === id) return;
    selectionRef.current = id;
    detailAbort.current?.abort();
    operationAbort.current?.abort();
    analysisAbort.current?.abort();
    setOperation("");
    setSelectedId(id);
    setAnalysis(null);
    setLocator("");
    setQuestion("");
    setDetail(null);
    setDetailError("");
    setCompareId(null);
    setReplacement(false);
  }
  function startOperation(name: "upload" | "retry" | "analysis") {
    const controller = new AbortController();
    operationAbort.current?.abort();
    operationAbort.current = controller;
    setOperation(name);
    return controller;
  }
  async function upload(file: File, replaceId?: string) {
    if (busy) return;
    setError("");
    setNotice("");
    if (file.size > 10 * 1024 * 1024) {
      setError("This file exceeds the 10 MB upload limit. Choose a smaller file.");
      return;
    }
    if (!/\.(pdf|docx|txt|md)$/i.test(file.name)) {
      setError("Choose a PDF, DOCX, TXT, or Markdown file.");
      return;
    }
    const controller = startOperation("upload");
    try {
      const doc = await api.upload(file, replaceId, controller.signal);
      if (controller.signal.aborted) return;
      await refresh(controller.signal);
      if (controller.signal.aborted) return;
      chooseDocument(doc.document_id);
      setNotice(
        replaceId
          ? doc.document_id === replaceId
            ? "The uploaded content matches this document. The existing ready version was kept."
            : doc.status === "ready"
              ? "The replacement is ready. The earlier version is no longer current."
              : "The replacement was received. The earlier version remains current until the replacement is verified and ready."
          : "Your file was received. Its actual processing status appears below.",
      );
      setReplacement(false);
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e));
    } finally {
      if (!controller.signal.aborted) setOperation("");
      if (input.current) input.current.value = "";
    }
  }
  async function retry() {
    if (!selected || busy) return;
    const controller = startOperation("retry");
    setError("");
    try {
      await api.retry(selected.document_id, controller.signal);
      if (controller.signal.aborted) return;
      await refresh(controller.signal);
      if (controller.signal.aborted) return;
      setNotice(
        "The processing retry completed. Check the status and any remaining error below.",
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e));
    } finally {
      if (!controller.signal.aborted) setOperation("");
    }
  }
  async function analyze(event?: FormEvent) {
    event?.preventDefault();
    if (!selected || selected.status !== "ready" || busy) return;
    const id = selected.document_id;
    const abort = startOperation("analysis");
    analysisAbort.current?.abort();
    analysisAbort.current = abort;
    setError("");
    try {
      const data = await api.analysis(
        id,
        {
          ...(question.trim() ? { question: question.trim() } : {}),
          ...(locator ? { locator } : {}),
        },
        abort.signal,
      );
      if (!abort.signal.aborted && selectionRef.current === id) {
        setAnalysis(data);
        setCompareId(data.comparison.passages[0]?.passage_id ?? null);
        setTab("points");
      }
    } catch (e) {
      if (!abort.signal.aborted && !isAbort(e)) setError(errorMessage(e));
    } finally {
      if (!abort.signal.aborted && analysisAbort.current === abort) setOperation("");
    }
  }
  async function remove() {
    if (!selected || deleting) return;
    const id = selected.document_id;
    const controller = new AbortController();
    operationAbort.current = controller;
    setDeleting(true);
    setError("");
    try {
      const result = await api.deleteDocument(id, controller.signal);
      if (controller.signal.aborted) return;
      setConfirm(false);
      // The successful mutation owns selection reset, while its refresh remains cancellable.
      selectionRef.current = null;
      setSelectedId(null);
      setDetail(null);
      setAnalysis(null);
      setDocuments((previous) =>
        previous.flatMap((doc) =>
          doc.document_id !== id
            ? [doc]
            : result.status === "deleted"
              ? []
              : [{ ...doc, status: "deletion_pending" }],
        ),
      );
      setNotice(
        result.status === "deleted"
          ? "The API confirmed deletion of this document."
          : "Search access was revoked. Storage cleanup is still pending; refresh or retry deletion to check completion.",
      );
      window.requestAnimationFrame(() => listHeading.current?.focus());
      await refresh(controller.signal);
    } catch (e) {
      if (!controller.signal.aborted) {
        setConfirm(false);
        setError(errorMessage(e));
      }
    } finally {
      if (!controller.signal.aborted) setDeleting(false);
    }
  }
  return (
    <div>
      <header className="page-heading">
        <span className="eyebrow">My documents / private workspace</span>
        <h1>
          A clearer view
          <br />
          <em>of your document.</em>
        </h1>
        <p>
          Read the clauses, ask about the text, and compare with captured legal sources.
          Your private documents remain separate from the public corpus.
        </p>
      </header>
      <div className="card upload-card">
        <div className="upload-icon">
          <Icon name="file" size={30} />
        </div>
        <div>
          <h2>
            {replacement && selected
              ? `Replace ${selected.filename}`
              : "Bring a document into focus"}
          </h2>
          <p className="muted">
            PDF, DOCX, TXT or Markdown · up to 10 MB. Scanned, encrypted or unsafe files
            may be rejected.
          </p>
          <p className="small muted">
            This local demo uses a private session, not production identity. Use a
            synthetic sample for a public demonstration.
          </p>
        </div>
        <div className="upload-actions">
          <input
            ref={input}
            tabIndex={-1}
            aria-label={
              replacement ? "Choose replacement document" : "Choose document to upload"
            }
            className="file-input"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            disabled={Boolean(busy)}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file)
                void upload(file, replacement ? (selectedId ?? undefined) : undefined);
            }}
          />
          <button
            className="primary"
            disabled={Boolean(busy)}
            onClick={() => input.current?.click()}
          >
            <Icon name="plus" />
            {busy === "upload"
              ? "Uploading…"
              : replacement
                ? "Choose replacement"
                : "Upload document"}
          </button>
          <button
            className="text-button"
            disabled={Boolean(busy)}
            onClick={() => {
              if (replacement) setReplacement(false);
              else
                void upload(
                  new File([SAMPLE_LEASE], "synthetic-sample-lease.txt", {
                    type: "text/plain",
                  }),
                );
            }}
          >
            {replacement ? "Cancel replacement" : "Try a synthetic sample lease ↗"}
          </button>
        </div>
      </div>
      {busy === "upload" && <Busy>Uploading and processing your actual file…</Busy>}
      {notice && (
        <div role="status" className="notice success">
          {notice}
        </div>
      )}
      {error && <ErrorNotice message={error} />}
      <div className="documents-grid">
        <aside className="card document-list" aria-label="Your documents">
          <div className="panel-heading row spread">
            <h2 ref={listHeading} tabIndex={-1}>
              Your documents <span className="count">{documents.length}</span>
            </h2>
            <button
              className="text-button"
              disabled={Boolean(busy)}
              onClick={() => {
                setError("");
                const signal = lifetime.current!.signal;
                void refresh(signal).catch((e) => {
                  if (!signal.aborted) setError(errorMessage(e));
                });
              }}
            >
              Refresh
            </button>
          </div>
          {busy === "list" && <Busy>Loading documents…</Busy>}
          {!documents.length && busy !== "list" && (
            <EmptyState title="A fresh workspace">
              <p>Upload your first document, or try the synthetic lease.</p>
            </EmptyState>
          )}
          {documents.map((doc) => (
            <button
              key={doc.document_id}
              className="document-item"
              aria-pressed={selectedId === doc.document_id}
              disabled={busy === "upload" || deleting}
              onClick={() => {
                if (selectionRef.current !== doc.document_id)
                  chooseDocument(doc.document_id);
                setError("");
                setReplacement(false);
              }}
            >
              <Icon name="file" />
              <span>
                <strong>{doc.filename}</strong>
                <span className="small muted">
                  {dateLabel(doc.created_at)} · {doc.section_count} sections
                </span>
                <Badge
                  tone={
                    doc.status === "ready"
                      ? "green"
                      : doc.status === "failed"
                        ? "red"
                        : "gold"
                  }
                >
                  {STATUS_LABELS[doc.status]}
                </Badge>
              </span>
            </button>
          ))}
        </aside>
        <div className="document-workspace">
          {!selected && (
            <div className="card">
              <EmptyState title="Your document, with context">
                <p>
                  Select a document to inspect its text and processing details. A ready
                  document can be analyzed and questioned.
                </p>
              </EmptyState>
            </div>
          )}
          {selected && (
            <>
              <section className="card document-detail">
                <div className="row spread wrap">
                  <div>
                    <span className="eyebrow">Private document</span>
                    <h2 className="document-filename">{selected.filename}</h2>
                  </div>
                  <Badge
                    tone={
                      selected.status === "ready"
                        ? "green"
                        : selected.status === "failed"
                          ? "red"
                          : "gold"
                    }
                  >
                    {STATUS_LABELS[selected.status]}
                  </Badge>
                </div>
                <ol className="processing-steps" aria-label="Processing progress">
                  {["Uploaded", "Text extracted", "Prepared for questions", "Ready"].map(
                    (step, i) => {
                      const level =
                        selected.status === "ready"
                          ? 4
                          : ["indexing", "verifying"].includes(selected.status)
                            ? 3
                            : selected.status === "chunking"
                              ? 2
                              : 1;
                      return (
                        <li key={step} className={i < level ? "complete" : ""}>
                          <span>
                            {i < level ? <Icon name="check" size={14} /> : i + 1}
                          </span>
                          {step}
                        </li>
                      );
                    },
                  )}
                </ol>
                {selected.error && (
                  <div className="notice error">
                    <strong>Processing needs attention</strong>
                    <p>{selected.error}</p>
                  </div>
                )}
                {selected.status === "failed" && (
                  <button className="secondary" onClick={retry} disabled={Boolean(busy)}>
                    {busy === "retry" ? "Retrying…" : "Retry processing"}
                  </button>
                )}
                {ACTIVE.includes(selected.status) &&
                  selected.status !== "deletion_pending" && (
                    <Busy>
                      {STATUS_LABELS[selected.status]}. Status refreshes automatically.
                    </Busy>
                  )}
                {selected.status === "deletion_pending" && (
                  <div className="notice">
                    <p>
                      Search access is revoked. Cleanup is pending. Retry deletion to
                      reconcile remaining storage.
                    </p>
                    <button className="secondary" onClick={() => setConfirm(true)}>
                      Retry deletion
                    </button>
                  </div>
                )}
                <div className="document-actions row wrap">
                  <a
                    className="text-button"
                    href={`/api/v1/documents/${encodeURIComponent(selected.document_id)}/download`}
                    download
                  >
                    Download original ↗
                  </a>
                  <button
                    className="text-button"
                    disabled={Boolean(busy) || selected.status === "deletion_pending"}
                    onClick={() => setReplacement(true)}
                  >
                    Replace file
                  </button>
                  <button
                    className="text-button destructive"
                    disabled={Boolean(busy)}
                    onClick={() => setConfirm(true)}
                  >
                    Delete document
                  </button>
                </div>
                <details className="advanced">
                  <summary>Processing details</summary>
                  <dl className="metadata">
                    <dt>Document ID</dt>
                    <dd>{selected.document_id}</dd>
                    <dt>Version</dt>
                    <dd>{selected.version}</dd>
                    <dt>Hash</dt>
                    <dd>{selected.content_hash}</dd>
                    <dt>Searchable passages</dt>
                    <dd>{selected.passage_count}</dd>
                  </dl>
                  <pre>{JSON.stringify(selected.processing, null, 2)}</pre>
                </details>
              </section>
              {busy === "detail" && <Busy>Opening document text…</Busy>}
              {detailError && (
                <ErrorNotice
                  message={detailError}
                  onRetry={() => setDetailRevision((previous) => previous + 1)}
                />
              )}
              {selected.status === "ready" && detail && (
                <>
                  <section className="card document-review">
                    <div className="segmented" aria-label="Document view">
                      <button
                        aria-pressed={tab === "points"}
                        onClick={() => setTab("points")}
                      >
                        Key points &amp; questions
                      </button>
                      <button
                        aria-pressed={tab === "text"}
                        onClick={() => setTab("text")}
                      >
                        Read document text
                      </button>
                    </div>
                    {tab === "text" ? (
                      <div className="sections-list">
                        {detail.sections.length ? (
                          detail.sections.map((section, i) => (
                            <article
                              key={`${section.locator}-${i}`}
                              id={`section-${i}`}
                              tabIndex={-1}
                            >
                              <span className="eyebrow">{section.locator}</span>
                              <h3>{section.title}</h3>
                              <p className="document-text">{section.text}</p>
                              <button
                                className="text-button"
                                onClick={() => {
                                  setLocator(section.locator);
                                  setTab("points");
                                }}
                              >
                                Use this section in a question ↗
                              </button>
                            </article>
                          ))
                        ) : (
                          <p className="muted">
                            No sections were supplied by the parser.
                          </p>
                        )}
                      </div>
                    ) : (
                      <>
                        <form onSubmit={analyze} className="document-question">
                          <h3>Understand what the document says</h3>
                          <p className="muted">
                            Extract literal facts and clauses, then compare related public
                            passages. Considerations are rule-based prompts for review.
                          </p>
                          <label htmlFor="document-question">
                            Ask about this document{" "}
                            <span className="muted">(optional)</span>
                          </label>
                          <textarea
                            id="document-question"
                            value={question}
                            maxLength={2000}
                            rows={3}
                            onChange={(e) => setQuestion(e.target.value)}
                            placeholder="What does this lease say about the security deposit?"
                          />
                          <label htmlFor="document-section">Focus on a section</label>
                          <select
                            id="document-section"
                            value={locator}
                            onChange={(e) => setLocator(e.target.value)}
                          >
                            <option value="">Whole document</option>
                            {detail.sections.map((section, i) => (
                              <option
                                key={`${section.locator}-${i}`}
                                value={section.locator}
                              >
                                {section.locator} — {section.title}
                              </option>
                            ))}
                          </select>
                          <button
                            className="primary"
                            type="submit"
                            disabled={Boolean(busy)}
                          >
                            {busy === "analysis"
                              ? "Reading passages…"
                              : question.trim()
                                ? "Ask about the document"
                                : "Analyze & compare sources"}
                            <Icon name="arrow" />
                          </button>
                        </form>
                        {busy === "analysis" && (
                          <Busy>
                            Extracting document clauses and retrieving a public-source
                            comparison…
                          </Busy>
                        )}
                        {analysis && (
                          <div className="analysis">
                            <h3 ref={analysisHeading} tabIndex={-1} className="eyebrow">
                              Document summary
                            </h3>
                            <p className="analysis-summary">{analysis.summary}</p>
                            <h3>Key points in the text</h3>
                            {analysis.findings.map((finding, i) => (
                              <article className={`finding ${finding.kind}`} key={i}>
                                <div className="row spread wrap">
                                  <Badge
                                    tone={
                                      finding.kind === "consideration" ||
                                      finding.kind === "evidence_gap"
                                        ? "gold"
                                        : "neutral"
                                    }
                                  >
                                    {
                                      {
                                        contract_text: "Contract text",
                                        document_fact: "Literal document fact",
                                        consideration: "Needs closer review",
                                        evidence_gap: "Evidence gap",
                                      }[finding.kind]
                                    }
                                  </Badge>
                                  <span className="small muted">{finding.locator}</span>
                                </div>
                                <h4>{finding.title}</h4>
                                <p>{finding.text}</p>
                                <p className="small muted">
                                  {["contract_text", "document_fact"].includes(
                                    finding.kind,
                                  )
                                    ? finding.verified
                                      ? "Text identity checked; underlying facts are not independently verified."
                                      : "Exact section text; passage match not established. Underlying facts are not independently verified."
                                    : "Rule-based consideration; legal applicability and underlying facts are not verified."}
                                </p>
                                <button
                                  className="text-button"
                                  onClick={() => {
                                    setLocator(finding.locator);
                                    setTab("text");
                                  }}
                                >
                                  Read the document text ↗
                                </button>
                              </article>
                            ))}
                            <div className="notice">
                              <strong>What this review does not establish</strong>
                              <ul>
                                {analysis.limitations.map((limit, i) => (
                                  <li key={i}>{limit}</li>
                                ))}
                              </ul>
                              <p>
                                No lawfulness verdict, risk score, identity check, or
                                payment verification is provided.
                              </p>
                            </div>
                            <details className="advanced">
                              <summary>Analysis method &amp; references</summary>
                              <p>{analysis.method}</p>
                              <pre>
                                {JSON.stringify(
                                  analysis.findings.map((f) => ({
                                    title: f.title,
                                    passage_ids: f.passage_ids,
                                  })),
                                  null,
                                  2,
                                )}
                              </pre>
                            </details>
                          </div>
                        )}
                      </>
                    )}
                  </section>
                  {analysis?.answer && (
                    <ResearchAnswer
                      result={analysis.answer}
                      title="Answer from your document"
                    />
                  )}
                  {analysis && (
                    <div className="comparison">
                      <PassageInspector
                        passages={analysis.comparison.passages}
                        selected={compareId}
                        onSelect={setCompareId}
                        title="Compare with legal sources"
                      />
                      {analysis.comparison.limitations.length > 0 && (
                        <div className="notice">
                          <ul>
                            {analysis.comparison.limitations.map((limit, i) => (
                              <li key={i}>{limit}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
      {confirm && selected && (
        <ConfirmDialog
          title="Permanently delete this document?"
          confirmLabel="Delete document"
          busy={deleting}
          onClose={() => setConfirm(false)}
          onConfirm={() => void remove()}
        >
          <p>
            <strong>{selected.filename}</strong> will become unavailable for search and
            review. The API will attempt to remove its file, extracted text and indexed
            passages.
          </p>
          <p>
            All saved research run history in this workspace will also be removed because
            questions may contain copied private text, including questions searched
            against public sources. Frozen public evaluation reports are retained. If file
            cleanup is pending, the interface will say so.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
