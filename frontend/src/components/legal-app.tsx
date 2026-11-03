"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ensureSession, errorMessage } from "@/lib/api";
import type { Session } from "@/lib/types";
import { Documents } from "./documents";
import { Evaluations } from "./evaluations";
import { Reference } from "./reference";
import { EXAMPLES, Research } from "./research";
import { Badge, Busy, ErrorNotice, Icon } from "./ui";

type View = "home" | "research" | "documents" | "evaluations" | "reference";
const LABELS: Record<View, string> = {
  home: "Home",
  research: "Research",
  documents: "My documents",
  evaluations: "Evaluation lab",
  reference: "Project reference",
};
function validView(value: string): View {
  return Object.hasOwn(LABELS, value) ? (value as View) : "home";
}

export function LegalApp() {
  const [view, setView] = useState<View>("home");
  const [visited, setVisited] = useState<View[]>(["home"]);
  const [developer, setDeveloper] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [sessionBusy, setSessionBusy] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [initialQuestion, setInitialQuestion] = useState("");
  const main = useRef<HTMLElement>(null);
  const consumeQuestion = useCallback(() => setInitialQuestion(""), []);
  async function connect() {
    setSessionBusy(true);
    setSessionError("");
    try {
      setSession(await ensureSession());
    } catch (e) {
      setSessionError(errorMessage(e));
    } finally {
      setSessionBusy(false);
    }
  }
  useEffect(() => {
    void connect();
    const change = () => {
      const hash = window.location.hash.slice(1);
      if (hash && !Object.hasOwn(LABELS, hash)) return;
      const next = validView(hash);
      setView(next);
      setVisited((previous) =>
        previous.includes(next) ? previous : [...previous, next],
      );
      if (next === "evaluations" || next === "reference") setDeveloper(true);
    };
    change();
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    const expired = () => {
      setSession(null);
      setSessionError(
        "Your local session expired. Reconnect to create a fresh private workspace. Previous documents are not carried into a new workspace.",
      );
    };
    window.addEventListener("legalai:session-expired", expired);
    return () => window.removeEventListener("legalai:session-expired", expired);
  }, []);
  useEffect(() => {
    if (!developer) return;
    const close = (event: PointerEvent) => {
      if (
        window.innerWidth <= 700 &&
        !(event.target as Element).closest(".developer-nav")
      )
        setDeveloper(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [developer]);
  function navigate(next: View, question = "") {
    setView(next);
    setVisited((previous) => (previous.includes(next) ? previous : [...previous, next]));
    if (window.innerWidth <= 700) setDeveloper(false);
    if (question) setInitialQuestion(question);
    window.location.hash = next;
    main.current?.focus();
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function navButton(next: View, icon: "home" | "search" | "file" | "chart" | "book") {
    return (
      <button
        key={next}
        type="button"
        aria-current={view === next ? "page" : undefined}
        onClick={() => navigate(next)}
      >
        <Icon name={icon} />
        <span>{LABELS[next]}</span>
      </button>
    );
  }
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to main content
      </a>
      <div className="app-shell">
        <aside className="sidebar">
          <button
            className="brand"
            aria-label="legal.ai home"
            onClick={() => navigate("home")}
          >
            <span className="brand-symbol" aria-hidden="true">
              l.
            </span>
            <span>
              legal<span className="brand-ai">.ai</span>
            </span>
          </button>
          <p className="edition">Clarity, with sources.</p>
          <nav aria-label="Main navigation">
            <p className="nav-label">Your workspace</p>
            <div className="nav-links">
              {navButton("home", "home")}
              {navButton("research", "search")}
              {navButton("documents", "file")}
            </div>
            <div
              className="developer-nav"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setDeveloper(false);
                  event.currentTarget
                    .querySelector<HTMLButtonElement>(".developer-toggle")
                    ?.focus();
                }
              }}
            >
              <button
                className="developer-toggle"
                aria-expanded={developer}
                aria-controls="developer-links"
                onClick={() => setDeveloper(!developer)}
              >
                Developer tools <span aria-hidden="true">{developer ? "−" : "+"}</span>
              </button>
              <div id="developer-links" className="nav-links" hidden={!developer}>
                {navButton("evaluations", "chart")}
                {navButton("reference", "book")}
              </div>
            </div>
          </nav>
          <div className="sidebar-bottom">
            <div className="scope-note">
              <div className="row">
                <span className="status-dot" />
                <strong>Local &amp; offline</strong>
              </div>
              <p>
                Source-linked extraction.
                <br />
                No model or Pinecone calls.
              </p>
            </div>
            <div className="workspace-identity">
              <span className="avatar" aria-hidden="true">
                L
              </span>
              <div>
                <strong>
                  {session
                    ? "Private local session"
                    : sessionBusy
                      ? "Connecting locally…"
                      : "API disconnected"}
                </strong>
                <span>
                  {session
                    ? "Local demo · not production SSO"
                    : "Start the local API to continue"}
                </span>
              </div>
            </div>
            <button
              className="text-button reconnect"
              disabled={sessionBusy}
              onClick={() => void connect()}
            >
              Reconnect session
            </button>
          </div>
        </aside>
        <div className="app-main">
          <header className="topbar">
            <div className="breadcrumb">
              Workspace <span aria-hidden="true">/</span> <strong>{LABELS[view]}</strong>
            </div>
            <div className="row">
              <Badge tone="green">
                <span className="status-dot" />
                Offline edition
              </Badge>
              <span className="topbar-note">Evidence before confidence</span>
            </div>
          </header>
          <main id="main" ref={main} tabIndex={-1} className="content">
            <div className="content-topline">
              <span className="eyebrow">Legal questions, made more legible</span>
              <span className="small muted">California · landlord–tenant</span>
            </div>
            {sessionError && (
              <ErrorNotice message={sessionError} onRetry={() => void connect()} />
            )}
            {view === "home" && (
              <Home
                onResearch={(question) => navigate("research", question)}
                onDocuments={() => navigate("documents")}
              />
            )}
            {view !== "home" && !session && sessionBusy && (
              <div className="card loading-card">
                <Busy>Preparing your private local workspace…</Busy>
              </div>
            )}
            {session && (
              <div className="workspace-content" key={session.workspace_id}>
                <section hidden={view !== "research"} aria-label="Research">
                  {visited.includes("research") && (
                    <Research
                      initialQuestion={initialQuestion}
                      onQuestionConsumed={consumeQuestion}
                    />
                  )}
                </section>
                <section hidden={view !== "documents"} aria-label="My documents">
                  {visited.includes("documents") && <Documents />}
                </section>
                <section hidden={view !== "evaluations"} aria-label="Evaluation lab">
                  {visited.includes("evaluations") && <Evaluations />}
                </section>
                <section hidden={view !== "reference"} aria-label="Project reference">
                  {visited.includes("reference") && <Reference />}
                </section>
              </div>
            )}
            <footer className="app-footer">
              <span>legal.ai · Independent local project</span>
              <span>Explanations of sources. No legal determinations.</span>
            </footer>
          </main>
        </div>
      </div>
    </>
  );
}

function Home({
  onResearch,
  onDocuments,
}: {
  onResearch: (question?: string) => void;
  onDocuments: () => void;
}) {
  return (
    <div className="home">
      <header className="home-heading">
        <div className="row home-kicker">
          <span className="short-rule" />
          <span className="eyebrow">A little more understanding</span>
        </div>
        <h1>
          Legal questions.
          <br />
          Clearer <em>starting points.</em>
        </h1>
        <p>
          Understand a legal question or document through source-linked explanations. See
          what the text says, where it comes from, and what still needs checking.
        </p>
      </header>
      <div className="task-grid">
        <button className="task-card task-primary" onClick={() => onResearch()}>
          <span className="task-icon">
            <Icon name="search" size={27} />
          </span>
          <span className="task-label">01 / Research</span>
          <strong>Ask a legal question</strong>
          <span>
            Explore California landlord–tenant law, with sources you can inspect.
          </span>
          <span className="task-action">
            Start a question <Icon name="arrow" />
          </span>
        </button>
        <button className="task-card task-secondary" onClick={onDocuments}>
          <span className="task-icon">
            <Icon name="file" size={27} />
          </span>
          <span className="task-label">02 / Document review</span>
          <strong>Review a document</strong>
          <span>Find clauses, ask about the text, and compare with legal sources.</span>
          <span className="task-action">
            Bring a document <Icon name="arrow" />
          </span>
        </button>
      </div>
      <div className="home-examples">
        <div>
          <span className="eyebrow">Not sure where to begin?</span>
          <h2>A few questions to start with.</h2>
        </div>
        <div className="home-example-list">
          {EXAMPLES.map((question, i) => (
            <button key={question} onClick={() => onResearch(question)}>
              <span className="example-index">0{i + 1}</span>
              <span>{question}</span>
              <span aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
      </div>
      <div className="home-principles">
        <div>
          <Icon name="book" />
          <p>
            <strong>Read the evidence.</strong>
            <span>Exact source text is always within reach.</span>
          </p>
        </div>
        <div>
          <Icon name="shield" />
          <p>
            <strong>Keep the limits visible.</strong>
            <span>Coverage gaps are part of the answer.</span>
          </p>
        </div>
        <div>
          <Icon name="file" />
          <p>
            <strong>Start within the scope.</strong>
            <span>A small California landlord–tenant corpus.</span>
          </p>
        </div>
      </div>
    </div>
  );
}
