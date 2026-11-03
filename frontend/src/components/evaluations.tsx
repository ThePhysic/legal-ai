"use client";

import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Configuration, Dataset, EvaluationRun } from "@/lib/types";
import { Badge, Busy, dateLabel, EmptyState, ErrorNotice, Icon } from "./ui";

function metricLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\b(mrr|ndcg|p50|p95)\b/gi, (value) => value.toUpperCase());
}
function metricValue(value: unknown): string {
  if (value === null || value === undefined) return "Not assessed";
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function Evaluations() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [dataset, setDataset] = useState("");
  const [configurations, setConfigurations] = useState<Configuration[]>([
    "lexical",
    "dense",
    "hybrid",
    "rerank",
  ]);
  const [selected, setSelected] = useState<EvaluationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setBusy(true);
    setError("");
    try {
      const data = await api.evaluations();
      setDatasets(data.datasets);
      setRuns(data.runs);
      setDataset((previous) => previous || data.datasets[0]?.id || "");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function run() {
    if (!dataset || !configurations.length) return;
    setRunning(true);
    setError("");
    try {
      const data = await api.evaluate(dataset, configurations);
      setSelected(data);
      const listing = await api.evaluations();
      setRuns(listing.runs);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRunning(false);
    }
  }
  async function select(id: string) {
    setBusy(true);
    setError("");
    try {
      setSelected(await api.evaluation(id));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const selectedDataset = datasets.find((d) => d.id === dataset);
  const metricKeys = selected
    ? [...new Set(selected.configurations.flatMap((c) => Object.keys(c.metrics)))]
    : [];
  return (
    <div>
      <header className="page-heading">
        <div className="row wrap">
          <span className="eyebrow">Developer tools / evaluation</span>
          <Badge tone="gold">Measured local runs</Badge>
        </div>
        <h1>
          Test the retrieval.
          <br />
          <em>Keep the evidence.</em>
        </h1>
        <p>
          Run the versioned starter benchmark against local configurations. Every figure
          below comes from a saved API run; no demonstration metrics are substituted.
        </p>
      </header>
      <div className="notice">
        <strong>What these measurements mean</strong>
        <p>
          Retrieval labels are starter benchmark judgments, not independent human
          assessment. Citation identity checks do not measure semantic correctness. Live
          Pinecone, model quality, deployed performance and cloud cost remain unvalidated.
        </p>
      </div>
      <section className="card evaluation-controls">
        <div className="form-grid">
          <label htmlFor="evaluation-dataset">
            Benchmark dataset
            <select
              id="evaluation-dataset"
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              disabled={running || !datasets.length}
            >
              {!datasets.length && <option value="">No datasets available</option>}
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} · {d.count} cases
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Local configurations</legend>
            <div className="checkboxes">
              {(["lexical", "dense", "hybrid", "rerank"] as Configuration[]).map((c) => (
                <label key={c}>
                  <input
                    type="checkbox"
                    checked={configurations.includes(c)}
                    disabled={running}
                    onChange={(e) =>
                      setConfigurations((previous) =>
                        e.target.checked
                          ? [...previous, c]
                          : previous.filter((x) => x !== c),
                      )
                    }
                  />
                  {
                    {
                      lexical: "BM25",
                      dense: "Local vector",
                      hybrid: "Hybrid",
                      rerank: "Rerank",
                    }[c]
                  }
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        {selectedDataset && (
          <p className="small muted">
            Revision {selectedDataset.revision} · {selectedDataset.judgment_provenance}
          </p>
        )}
        <button
          className="primary"
          disabled={busy || running || !dataset || !configurations.length}
          onClick={() => void run()}
        >
          {running ? "Running local benchmark…" : "Run evaluation"}
          <Icon name="arrow" />
        </button>
      </section>
      {running && (
        <Busy>Running the benchmark and recording per-question measurements…</Busy>
      )}
      {error && <ErrorNotice message={error} onRetry={() => void load()} />}
      {busy && <Busy>Loading saved evaluation data…</Busy>}
      <div className="evaluation-layout">
        <aside className="card run-list">
          <div className="panel-heading row spread">
            <h2>Saved runs</h2>
            <button
              className="text-button"
              disabled={busy || running}
              onClick={() => void load()}
            >
              Refresh
            </button>
          </div>
          {!runs.length && !busy && (
            <EmptyState title="No results yet" icon="chart">
              <p>Run an evaluation to create a measured comparison.</p>
            </EmptyState>
          )}
          {runs.map((r) => (
            <button
              key={r.evaluation_id}
              className="run-item"
              aria-pressed={selected?.evaluation_id === r.evaluation_id}
              onClick={() => void select(r.evaluation_id)}
              disabled={busy || running}
            >
              <strong>{r.dataset_id}</strong>
              <span className="small muted">
                {dateLabel(r.created_at)} · {r.status}
              </span>
              <span className="mono">{r.evaluation_id.slice(0, 12)}</span>
            </button>
          ))}
        </aside>
        <div>
          {!selected && (
            <div className="card">
              <EmptyState title="A reproducible comparison" icon="chart">
                <p>
                  Select a saved run or start a new evaluation. Missing and unassessed
                  values will remain visible.
                </p>
              </EmptyState>
            </div>
          )}
          {selected && (
            <section className="card evaluation-result">
              <div className="row spread wrap">
                <div>
                  <span className="eyebrow">Actual benchmark result</span>
                  <h2>{selected.dataset_id}</h2>
                </div>
                <Badge
                  tone={
                    selected.status === "completed" || selected.status === "complete"
                      ? "green"
                      : "gold"
                  }
                >
                  {selected.status}
                </Badge>
              </div>
              <p className="muted">{selected.method}</p>
              <p className="small muted">
                Dataset revision {selected.dataset_revision} ·{" "}
                {dateLabel(selected.created_at)}
              </p>
              <div className="table-scroll">
                <table>
                  <caption>
                    Measured metrics by configuration. Null or missing values are not
                    assessed.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Metric</th>
                      {selected.configurations.map((c) => (
                        <th key={c.configuration} scope="col">
                          {c.configuration}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metricKeys.map((key) => (
                      <tr key={key}>
                        <th scope="row">{metricLabel(key)}</th>
                        {selected.configurations.map((c) => (
                          <td key={c.configuration}>{metricValue(c.metrics[key])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="small muted">
                Units and denominator definitions are preserved in the run manifest. Local
                CPU execution is not a cloud cost estimate.
              </p>
              <div className="notice">
                <strong>Judgment provenance</strong>
                <p>{selected.judgment_provenance}</p>
                <ul>
                  {selected.limitations.map((limit, i) => (
                    <li key={i}>{limit}</li>
                  ))}
                </ul>
              </div>
              {selected.configurations.map((c) => (
                <details className="advanced" key={c.configuration}>
                  <summary>
                    {c.configuration}: manifest &amp; per-question results (
                    {c.cases.length})
                  </summary>
                  <h3>Reproduction manifest</h3>
                  <pre>{JSON.stringify(c.manifest, null, 2)}</pre>
                  <h3>Preserved case results</h3>
                  {c.cases.map((item, i) => (
                    <details className="case-details" key={i}>
                      <summary>
                        Case {String(item.case_id ?? item.id ?? i + 1)}
                        {typeof item.question === "string" ? ` — ${item.question}` : ""}
                      </summary>
                      <pre>{JSON.stringify(item, null, 2)}</pre>
                    </details>
                  ))}
                </details>
              ))}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
