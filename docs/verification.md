# Offline release verification — November 3, 2026

This record covers the independently implemented local product. Tests used synthetic private documents and the frozen public statutory corpus. No Pinecone/model provider was called, no paid provider experiment ran, and no public service was deployed.

| Gate | Observed result |
| --- | --- |
| Complete Python suite | 295 passed; two upstream deprecation warnings |
| Python Ruff | API, evaluation, scripts, tests and examples pass |
| Frontend interaction suite | 15 passed |
| Frontend formatting and typecheck | Pass; route types generated before TypeScript, including a fresh scratch source copy without `.next` |
| Production build | Final API and Next.js Docker images built successfully |
| Real production browser flows | 38 passed, zero failures; [report](../artifacts/browser/report.json) |
| PostgreSQL/container/proxy smoke | 22 passed, zero failures; [report](../artifacts/container-smoke.json) |
| Python and TypeScript reference clients | Both returned source-linked research through the final local container API |
| Corpus integrity | Three official statutory snapshots, 122 passages; hashes, identities and size checks pass |
| Runtime Python dependency audit | No known vulnerabilities reported by pip-audit against exported locked runtime dependencies |
| Full frontend dependency audit | Zero known vulnerabilities reported by npm audit, including development dependencies |
| Source hygiene | Tracked-file credential/runtime gate and full-history Gitleaks scan pass; one exact historical empty-placeholder false positive is documented in security.md |

The final browser run used Chrome 156 against the production frontend at `http://127.0.0.1:3017` and API at `http://127.0.0.1:8017`. It exercised actual research with four retrieval methods, foreign jurisdiction and relative-date abstention, private parsing/Q&A/analysis, replacement/deletion/retry, run provenance and real evaluations. Nine foreign-session operations were denied. It observed zero uncaught browser exceptions and zero external page requests. All five views were checked at 360, 390, 768, 1024 and 1440 CSS pixels; key text contrast pairs, keyboard focus, modal handling and reduced motion were checked. The 720 CSS pixel layout check represents equivalent reflow at 200% zoom; native browser zoom was not emulated.

## Adversarial review

Independent **Astra, medium reasoning** reviews covered L0 design, L1–L4 implementation and the final offline product. Initial implementation findings led to fixes for PDF annotation actions, explicit conflicting evidence and replacement/retry lineage. Browser checks then prompted stronger personal-lawfulness and unrelated-topic abstention. The final review found and resolved three further defects:

- Explicit foreign state/country wording could receive California evidence. A broader deterministic jurisdiction guard now abstains, while a quoted street address does not dilute an otherwise in-scope California query.
- Relative historical wording could bypass unknown effective-date bounds. Relative time cues now require validated applicability rather than borrowing the capture date.
- DOCX tables were appended to the final section. Body-order extraction now keeps a table under its actual heading and preserves the first heading title.

The final reviewer independently ran 111 applicability/DOCX tests and 65 security/ingestion/evaluation tests, and reproduced the original 16 real-corpus negative checks. Its explicit final verdict was **“CLEAN — no remaining actionable complaints for the offline release.”** This is an automated adversarial review, not an independent human legal or accessibility assessment.

## Frozen measurement

Report `1a3813b0c17d40f599526eed2fb9c85b` in [starter.json](../evaluations/reports/starter.json) was regenerated after the final implementation fixes and separately checked against the current normalized code fingerprints. Its 28 author-labeled cases and source identities are unchanged. Dataset SHA-256: `42806690e8afdf6af8d2e2895a2da272689eec844d6f6b14078a81b8deb62f2f`.

Lexical, hybrid and reranked configurations meet the documented starter retrieval thresholds. The deterministic hash-vector dense baseline fails Recall@10 and retains one false abstention. All ten required negative cases abstain per configuration; measured errors are zero. Citation identity/exact-quote checks pass mechanically. Independent semantic correctness/support and novice-user measurements remain null. Observed provider calls, tokens and dollars are all zero; this does not estimate infrastructure cost.

## External gates

Real Pinecone/model requests, independent human semantic/legal labels, production identity/HTTPS/retention validation, public deployment and novice-user research remain unexecuted. The user explicitly selected offline operation. Prepared adapters and mock transports do not satisfy these gates. See [design](design.md) and [deployment](deployment.md) for the separate enablement requirements.
