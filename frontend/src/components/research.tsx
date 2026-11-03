"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, errorMessage, isAbort } from "@/lib/api";
import type { Configuration, ResearchResponse } from "@/lib/types";
import { Badge, Busy, EmptyState, ErrorNotice, Icon, ResearchAnswer } from "./ui";

export const EXAMPLES = [
  "What paperwork must accompany a security deposit deduction?",
  "What does California law say about cleaning deductions from a security deposit?",
  "What does California law say about rental application screening fees?",
];

export function Research({
  initialQuestion,
  onQuestionConsumed,
}: {
  initialQuestion: string;
  onQuestionConsumed: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [configuration, setConfiguration] = useState<Configuration>("lexical");
  const [date, setDate] = useState("");
  const [jurisdiction, setJurisdiction] = useState("US-CA");
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (initialQuestion) {
      setQuestion(initialQuestion);
      onQuestionConsumed();
      input.current?.focus();
    }
  }, [initialQuestion, onQuestionConsumed]);
  useEffect(() => () => controller.current?.abort(), []);
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!question.trim() || busy) return;
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await api.research(
          {
            question: question.trim(),
            jurisdiction,
            applicable_on: date || null,
            source_scope: "public",
            configuration,
            top_k: 5,
          },
          current.signal,
        ),
      );
    } catch (e) {
      if (!isAbort(e)) setError(errorMessage(e));
    } finally {
      if (controller.current === current) setBusy(false);
    }
  }
  function cancel() {
    controller.current?.abort();
    setBusy(false);
  }
  return (
    <div>
      <header className="page-heading">
        <span className="eyebrow">Research / public legal sources</span>
        <h1>
          Start with a question.
          <br />
          <em>Stay close to the source.</em>
        </h1>
        <p>
          Explore a small captured collection of California landlord–tenant statutes.
          Every explanation comes with the passages behind it.
        </p>
      </header>
      <form className="card query-card" onSubmit={submit}>
        <label className="field-label" htmlFor="research-question">
          What would you like to understand?
        </label>
        <textarea
          ref={input}
          id="research-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={2000}
          required
          rows={3}
          placeholder="For example, what paperwork accompanies a security deposit deduction?"
        />
        <div className="query-footer">
          <div className="row wrap">
            <Badge tone="green">California landlord–tenant</Badge>
            <span className="small muted">Public sources · offline extraction</span>
          </div>
          <div className="row">
            {busy && (
              <button className="secondary" type="button" onClick={cancel}>
                Cancel
              </button>
            )}
            <button className="primary" disabled={busy || !question.trim()} type="submit">
              {busy ? "Searching sources…" : "Search legal sources"}
              <Icon name="arrow" />
            </button>
          </div>
        </div>
        <details className="query-options">
          <summary>Question date &amp; search options</summary>
          <div className="form-grid">
            <label>
              What date does your question concern?
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <span className="small muted">
                Optional. Unknown effective dates can prevent a date-specific answer.
              </span>
            </label>
            <label>
              Jurisdiction
              <select
                value={jurisdiction}
                onChange={(e) => setJurisdiction(e.target.value)}
              >
                <option value="US-CA">California</option>
                <option value="US-NY">New York — outside this corpus</option>
                <option value="US">United States — coverage not established</option>
              </select>
            </label>
            <label>
              Retrieval method
              <select
                value={configuration}
                onChange={(e) => setConfiguration(e.target.value as Configuration)}
              >
                <option value="lexical">Exact-term baseline (BM25)</option>
                <option value="dense">Local vector baseline</option>
                <option value="hybrid">Combined local retrieval</option>
                <option value="rerank">Local retrieval + reranking</option>
              </select>
              <span className="small muted">
                All choices run locally. None uses a model provider or Pinecone.
              </span>
            </label>
          </div>
        </details>
      </form>
      <div className="examples-row">
        <span className="small muted">Try a question</span>
        {EXAMPLES.map((example, i) => (
          <button
            key={example}
            className="example-chip"
            onClick={() => {
              setQuestion(example);
              input.current?.focus();
            }}
            disabled={busy}
          >
            {["Deposit paperwork", "Cleaning deductions", "Screening fees"][i]} ↗
          </button>
        ))}
      </div>
      {busy && (
        <div className="card loading-card">
          <Busy>Retrieving source passages and checking citation identities…</Busy>
          <p className="muted">
            The answer uses local extraction. No model or paid provider is being called.
          </p>
        </div>
      )}
      {error && <ErrorNotice message={error} onRetry={() => void submit()} />}
      {!busy && result && <ResearchAnswer result={result} />}
      {!busy && !result && !error && (
        <div className="research-intro-grid">
          <div className="card">
            <EmptyState title="An answer you can inspect" icon="search">
              <p>
                Read a short explanation, see what the retrieved text supports, and open
                each passage in context.
              </p>
            </EmptyState>
          </div>
          <div className="quiet-note">
            <span className="eyebrow">A deliberately bounded starting point</span>
            <h3>Coverage has edges. We show them.</h3>
            <p>
              This collection does not cover every jurisdiction, date, exception, or
              individual circumstance. An evidence gap is a useful result.
            </p>
            <p className="small">
              Semantic support is not independently assessed; citation identity is checked
              separately.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
