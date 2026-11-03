"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Source } from "@/lib/types";
import { Badge, Busy, dateLabel, ErrorNotice } from "./ui";

export function Reference() {
  const [corpus, setCorpus] = useState<{
    sources: Source[];
    coverage: string[];
    limitations: string[];
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  async function load() {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setBusy(true);
    setError("");
    try {
      const data = await api.corpus(controller.signal);
      if (!controller.signal.aborted) setCorpus(data);
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  useEffect(() => {
    void load();
    return () => activeRequest.current?.abort();
  }, []);
  return (
    <div>
      <header className="page-heading">
        <span className="eyebrow">Developer tools / project reference</span>
        <h1>
          Understand the system.
          <br />
          <em>Know its boundaries.</em>
        </h1>
        <p>
          An independent local project for source-grounded legal research. The working
          product uses deterministic retrieval and extraction; provider integrations are
          deferred.
        </p>
      </header>
      <div className="reference-grid">
        <section className="card reference-card">
          <Badge tone="green">Working offline</Badge>
          <h2>From question to passage</h2>
          <ol className="reference-steps">
            <li>
              <strong>Scope the question.</strong>
              <span>
                California public statutory snapshots or your session’s private document
                text.
              </span>
            </li>
            <li>
              <strong>Retrieve local text.</strong>
              <span>
                BM25, deterministic local vector retrieval, reciprocal-rank fusion, or
                bounded reranking.
              </span>
            </li>
            <li>
              <strong>Extract the evidence.</strong>
              <span>
                Source-linked excerpts, literal document facts, and explicit evidence
                gaps.
              </span>
            </li>
            <li>
              <strong>Inspect the identity.</strong>
              <span>
                Source, version, locator, hash, saved run and configuration stay
                available.
              </span>
            </li>
          </ol>
        </section>
        <section className="card reference-card">
          <Badge tone="gold">Not yet validated</Badge>
          <h2>Limits that stay visible</h2>
          <ul className="limits-list">
            <li>No live model or Pinecone calls in this release.</li>
            <li>
              No independent semantic correctness or novice-participant usability study.
            </li>
            <li>
              No production SSO, deployment, historical coverage guarantee, or legal
              determination.
            </li>
            <li>
              Local demo sessions isolate workspaces; they are not production
              authentication.
            </li>
            <li>
              No OCR. Encrypted, scanned, oversized or unsafe documents may be rejected.
            </li>
          </ul>
          <p className="small muted">
            Future cloud adapters and deployment recipes do not establish that external
            services were exercised.
          </p>
        </section>
      </div>
      <section className="card reference-card corpus-reference">
        <div className="row spread wrap">
          <div>
            <span className="eyebrow">Public collection</span>
            <h2>Captured sources &amp; coverage</h2>
          </div>
          <button className="secondary" disabled={busy} onClick={() => void load()}>
            Refresh metadata
          </button>
        </div>
        {busy && <Busy>Loading actual corpus metadata…</Busy>}
        {error && <ErrorNotice message={error} onRetry={() => void load()} />}
        {corpus && (
          <>
            <div className="row wrap coverage-badges">
              {corpus.coverage.map((item) => (
                <Badge key={item}>{item}</Badge>
              ))}
            </div>
            <p className="muted">
              {corpus.sources.length} archived public{" "}
              {corpus.sources.length === 1 ? "source" : "sources"}. Unknown effective
              dates remain unknown; capture dates do not prove historical applicability.
            </p>
            <div className="corpus-grid">
              {corpus.sources.map((source) => (
                <details className="corpus-source" key={source.source_id}>
                  <summary>
                    {source.title}
                    <span className="small muted">
                      {source.publisher} · {source.jurisdiction}
                    </span>
                  </summary>
                  <dl className="metadata">
                    <dt>Source</dt>
                    <dd>{source.source_id}</dd>
                    <dt>Captured</dt>
                    <dd>{dateLabel(source.captured_at)}</dd>
                    <dt>Effective from</dt>
                    <dd>{dateLabel(source.effective_from)}</dd>
                    <dt>Effective through</dt>
                    <dd>{dateLabel(source.effective_to)}</dd>
                    <dt>Version</dt>
                    <dd>{source.version}</dd>
                    <dt>Rights basis</dt>
                    <dd>{source.rights_basis}</dd>
                    <dt>Hash</dt>
                    <dd>{source.content_hash}</dd>
                  </dl>
                  {/^https?:\/\//i.test(source.url) && (
                    <a href={source.url} target="_blank" rel="noreferrer">
                      Original publisher ↗
                    </a>
                  )}
                </details>
              ))}
            </div>
            <div className="notice">
              <ul>
                {corpus.limitations.map((limit, i) => (
                  <li key={i}>{limit}</li>
                ))}
              </ul>
            </div>
          </>
        )}
      </section>
      <section className="card reference-card">
        <span className="eyebrow">Integration reference</span>
        <h2>A small, inspectable API</h2>
        <p className="muted">
          The browser uses same-origin routes under <code>/api/v1</code>. The Next.js
          server forwards them to the configured local API. Workspace scope comes from the
          server-owned HttpOnly session.
        </p>
        <div className="table-scroll">
          <table>
            <caption>Core API operations</caption>
            <thead>
              <tr>
                <th scope="col">Route</th>
                <th scope="col">Purpose</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["POST /sessions", "Create a new isolated local workspace"],
                ["POST /research", "Source-linked extraction or explicit abstention"],
                ["POST /documents", "Validate, parse and index a private file"],
                [
                  "POST /documents/{id}/analysis",
                  "Document facts, Q&A and public-source comparison",
                ],
                [
                  "DELETE /documents/{id}",
                  "Revoke visibility and reconcile storage deletion",
                ],
                ["POST /evaluations", "Run the bounded starter benchmark locally"],
                ["GET /runs/{id}", "Inspect authorized configuration and provenance"],
              ].map(([route, purpose]) => (
                <tr key={route}>
                  <td>
                    <code>{route}</code>
                  </td>
                  <td>{purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">
          See the repository’s docs/api-contract.md, docs/design.md, and operational
          documentation for the full contract, threat model, source rights and deferred
          live gates.
        </p>
      </section>
    </div>
  );
}
