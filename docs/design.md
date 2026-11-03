# legal.ai: L0 design and acceptance contract

## Authorized scope and completion claims

Build an independent local full-stack product matching the November 2026 specification and approved UX proposal. The user explicitly selected **offline only** on November 3, 2026. Implement and test live adapters with mock transports, but do not contact Pinecone/model providers, provision infrastructure or deploy. Private GitHub publication is authorized. A completed offline release does not constitute live Pinecone validation, LLM semantic accuracy, production deployment or novice-participant research; those external gates remain explicitly deferred.

## Product and architecture

Next.js/React/TypeScript frontend, FastAPI/Pydantic API, SQLAlchemy metadata with SQLite for deterministic local use and PostgreSQL production configuration/migration, encrypted local object-store adapter, and a recoverable local ingestion worker. A modular monolith keeps ownership, source versions and run identities explicit. No queue/Redis/agent framework until justified.

First visit: two tasks (research and document review). Customer navigation is separate from developer evaluation/reference. Unlike the proposal, real free-form research and file parsing call the local API. Every answer states its execution method. Source excerpts and support checks remain inspectable; provenance is progressive disclosure. Local developer comparisons use actual measurements, not proposal fixture numbers.

## Security domains and identity

Public authoritative snapshots are distinct from private workspace documents. Opaque, randomly generated session tokens map to server-owned workspace IDs; anonymous local-demo session creation always creates a new workspace and cannot select another workspace. Cookies are HttpOnly/SameSite; SDK bearer authorization is supported. Mutating cookie requests validate Origin; production cookies require HTTPS. Search, sources, upload/status/download/analysis/delete, evaluations and traces authorize ownership. Private vector namespaces derive only from server identity. Unauthenticated or cross-owner IDs return no data. Demo identities are not production SSO.

Private bytes and extracted content are encrypted at rest with a runtime-only generated or operator-supplied key; metadata excludes raw text in telemetry. Local keys/runtime/session tokens are ignored. Production requires secret-managed keys, encrypted PostgreSQL/object storage, HTTPS and configured identity/rate limits. No real confidential documents in public demonstrations.

## Corpus and applicability

Start with a small captured set of official California landlord–tenant statutory text. Record publisher, exact URL, capture timestamp, type, jurisdiction, source hash, version, section locators, rights basis and any confirmed effective-date bounds. Government-edict text is separated from copyrighted editorial/guidance material. Do not infer redistribution permission solely from public availability. Never represent an unknown effective date or a capture date as proof of historical applicability. Historical/date-specific questions require matching validated source bounds, otherwise abstain or expose the gap. Refresh is an explicit import of a new snapshot, not a continuous-coverage promise.

Synthetic private samples and adversarial test sources are labeled separately and excluded from public authority answers.

## Ingestion and retrieval

Validate file signature/type and size, cap DOCX uncompressed size/pages/text/chunks, reject encrypted/scanned/unsafe files, parse PDF with pypdf and DOCX with python-docx, normalize sections and deterministic content hashes. Lifecycle: uploaded -> extracting -> chunking -> indexing -> verifying -> ready; failed/interrupted jobs are retryable, and never searchable prematurely. Idempotent content/version IDs prevent duplicate chunks. Deletion revokes search immediately and reconciles objects/vectors/metadata with a visible pending/failure state; replacement cannot leave two current versions searchable.

BM25 is the exact-term baseline. The deterministic offline vector path is explicitly a local vector baseline, not Pinecone or a production semantic model. Hybrid is reciprocal-rank fusion with stable-passage deduplication; bounded deterministic reranking is labeled. A real Pinecone adapter targets an existing configured dense index, derives namespaces and filters on the server, validates dimensions and source identities, times out and never silently substitutes offline results for live failures. Model/provider/index/version/schema/metric, top-k, fusion/reranker/context budgets and dataset identity are captured per run. Exact Pinecone SDK/API shape must be verified against current official docs and a pinned package before implementation; no index creation side effects.

## Grounding and analysis

Offline generation is extractive and deterministic: quote retrieved source text with claim/passsage/source/version/locator identity. Do not label extractive identity validation as independent semantic verification. Research returns structured claims, coverage gaps, method and limits; out-of-corpus, unresolved historical applicability, low-relevance, injected instructions and case-specific legal determinations abstain explicitly. Provider outages are distinct from insufficient evidence; no silent model-memory fallback. Live generation adapters validate structured output and references, but are disabled by default and never called in this authorized run.

Document analysis exposes literal facts and clauses, summaries/Q&A grounded in private passages, clearly labeled rule-based considerations and a public-source comparison with uncertainty. No lawfulness/risk verdict, identity/payment verification, or allegations-as-facts. Input text cannot alter tools, authorization or cost controls.

## Evaluation and proposed acceptance thresholds

Use a versioned starter benchmark with passage-level relevance labels and explicit judgment provenance. Author/agent labels are not represented as independent human review. Approximately 100 carefully reviewed questions is a later dataset target, not a fabricated completion count. Include identifiers, paraphrases, multi-source, date/jurisdiction gaps, conflict, document Q&A, injection and unanswerable cases.

Release gates for the local deterministic suite: zero unauthorized document/source/trace leakage; zero fabricated citation identities or cross-version references; all injected-instruction safety cases preserve authorization and source-only behavior; out-of-corpus/date-unsupported/case-verdict negative cases abstain; upload caps/rejected files do not become searchable; recovery produces no duplicate current chunks; deletion/replacement remove old visibility. Retrieval thresholds are explicitly starter-benchmark gates: Recall@10 >= 0.70 and MRR@10 >= 0.60 on answerable public cases for at least one documented local configuration, with failures retained in the report. Do not require every strategy to improve. Numerical semantic support/correctness claims await independently reviewed labels. Report p50/p95 search/answer latency, errors, token/provider usage and cost basis; local CPU execution cost is not a cloud-price estimate.

CI includes meaningful unit/integration/browser tests, secret/dependency checks, build/type checks, migrations and Docker configuration validation. Record unavailable environments rather than claiming their tests ran. Bounded live-provider tests and deployed smoke gates are separately authorized future work, not fulfilled by mocks.

## Milestone gates

- L0: reviewed architecture/contracts, rights/source manifest, threat model, acceptance and offline boundaries.
- L1: working local web/API, real parsing, private isolation, lexical retrieval and ingestion recovery.
- L2: all retrieval paths/adapters/filter/version contracts implemented and offline tested; actual Pinecone evidence explicitly deferred by user.
- L3: structured extraction/answers/citations/abstention and document analysis, with provider-generation and independent semantic judgment limits visible.
- L4: reproducible stored evaluation and measured comparison report with honest judgment provenance.
- L5: tested local demo/reference/CI/operational docs, plus a deployment recipe; cloud deployment remains unexecuted. Final Astra clean review and verified private GitHub push.

L6 memory, OCR, speech, multilingual and extensive agent workflows remain optional.
