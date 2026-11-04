# Offline release verification — November 3, 2026

This record covers the independently implemented local product. Tests used synthetic private documents and the frozen public statutory corpus. No Pinecone/model provider was called, no paid provider experiment ran, and no public service was deployed.

| Gate                                    | Observed result                                                                                                                                              |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Complete Python suite                   | 392 passed; two upstream deprecation warnings                                                                                                                |
| Python Ruff                             | API, evaluation, scripts, tests and examples pass                                                                                                            |
| Frontend interaction suite              | 30 passed                                                                                                                                                    |
| Frontend formatting and typecheck       | Pass; route types generated before TypeScript, including a fresh scratch source copy without `.next`                                                         |
| Production build                        | Final API and Next.js Docker images built successfully                                                                                                       |
| Real production browser flows           | 40 passed, zero failures; [report](../artifacts/browser/report.json)                                                                                         |
| PostgreSQL/container/proxy smoke        | 26 passed, zero failures; [report](../artifacts/container-smoke.json)                                                                                        |
| Python and TypeScript reference clients | Both returned source-linked research through the final local container API                                                                                   |
| Corpus integrity                        | Three official statutory snapshots, 122 passages; hashes, identities and size checks pass                                                                    |
| Runtime Python dependency audit         | No known vulnerabilities reported by pip-audit against exported locked runtime dependencies                                                                  |
| Full frontend dependency audit          | Zero known vulnerabilities reported by npm audit, including development dependencies                                                                         |
| Source hygiene                          | Tracked-file credential/runtime gate and full-history Gitleaks scan pass; one exact historical empty-placeholder false positive is documented in security.md |

The final browser run used Chrome 156 against the production frontend at `http://127.0.0.1:3017` and API at `http://127.0.0.1:8017`. It exercised actual research with four retrieval methods, foreign jurisdiction and relative-date abstention, private parsing/Q&A/analysis, replacement/deletion/retry, run provenance and real evaluations. Nine foreign-session operations were denied. It observed zero uncaught browser exceptions and zero external page requests. All five views were checked at 360, 390, 768, 1024 and 1440 CSS pixels; key text contrast pairs, keyboard focus, modal handling and reduced motion were checked. The 720 CSS pixel layout check represents equivalent reflow at 200% zoom; native browser zoom was not emulated.

## Adversarial review

Independent **Astra, medium reasoning** reviews covered L0 design, L1–L4 implementation and the final offline product. Initial implementation findings led to fixes for PDF annotation actions, explicit conflicting evidence and replacement/retry lineage. Browser checks then prompted stronger personal-lawfulness and unrelated-topic abstention. The final review found and resolved three further defects:

- Explicit foreign state/country wording could receive California evidence. A broader deterministic jurisdiction guard now abstains, while a quoted street address does not dilute an otherwise in-scope California query.
- Relative historical wording could bypass unknown effective-date bounds. Relative time cues now require validated applicability rather than borrowing the capture date.
- DOCX tables were appended to the final section. Body-order extraction now keeps a table under its actual heading and preserves the first heading title.

The final reviewer independently ran 111 applicability/DOCX tests and 65 security/ingestion/evaluation tests, and reproduced the original 16 real-corpus negative checks. Its explicit final verdict was **“CLEAN — no remaining actionable complaints for the offline release.”** This is an automated adversarial review, not an independent human legal or accessibility assessment.

## Frozen measurement

Report `ef724df0fa894a02b6d8701b87b2d796` in [starter.json](../evaluations/reports/starter.json) was regenerated after the second-audit fixes and separately checked against the current normalized code fingerprints. Its 28 author-labeled cases and source identities are unchanged. Dataset SHA-256: `42806690e8afdf6af8d2e2895a2da272689eec844d6f6b14078a81b8deb62f2f`.

Lexical, hybrid and reranked configurations meet the documented starter retrieval thresholds. The deterministic hash-vector dense baseline fails Recall@10 and retains one false abstention. All ten required negative cases abstain per configuration; measured errors are zero. Citation identity/exact-quote checks pass mechanically. Independent semantic correctness/support and novice-user measurements remain null. Observed provider calls, tokens and dollars are all zero; this does not estimate infrastructure cost.

## External gates

The [second audit](reaudit.md) records additional reproduced failures discovered after the initial approval, their fixes, expanded regression checks and renewed clean Astra reviews. The table above reflects that corrected release; the original milestone review details are retained as history.

Real Pinecone/model requests, independent human semantic/legal labels, production identity/HTTPS/retention validation, public deployment and novice-user research remain unexecuted. The user explicitly selected offline operation. Prepared adapters and mock transports do not satisfy these gates. See [design](design.md) and [deployment](deployment.md) for the separate enablement requirements.

## Presentation polish recheck — November 3, 2026

This later pass changes documentation, licensing wording and repository guidance only. The implementation, dependencies, screenshots, frozen corpus and committed evaluation reports remain unchanged from `95c21d650374b9acae4153d96f41c4fb93d715d8`. The license retains the owner's all-rights-reserved decision while removing its outdated claim that the source repository is private.

Checks actually run during the presentation pass:

| Command or inspection                                                                                                                              | Actual result                                                                                                                                                |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.venv\Scripts\python.exe -m pytest -q`                                                                                                            | 392 passed; the same two upstream deprecation warnings                                                                                                       |
| `npm.cmd test` from `frontend/`                                                                                                                    | 30 passed across five files                                                                                                                                  |
| `.venv\Scripts\python.exe -m evaluations run --runtime .local/presentation/evaluation-runtime --output .local/presentation/evaluation-report.json` | Completed with zero provider calls, tokens and provider dollars; all four retrieval-score rows match the committed report                                    |
| Prettier check of changed Markdown, plus `git diff --check`                                                                                        | Pass                                                                                                                                                         |
| Local Markdown/HTML link, anchor, image and numerical-claim checks                                                                                 | Pass; four README images have descriptive alternatives and resolve to existing assets                                                                        |
| Credential-format check and pinned Gitleaks 8.30.1 scan of changed documentation                                                                   | No matches/leaks reported; scanner archive checksum verified and tooling kept under ignored `.local/`                                                        |
| Read-only inspection of hosted CI                                                                                                                  | Latest recorded run [41721155295](https://github.com/ThePhysic/legal-ai/actions/runs/41721155295) passed for the unchanged base commit; no new run triggered |

The fresh benchmark is `f79ca732a3c04cccbf0ddb09b73966e6`. Dataset and label hashes, source/passage identities, corpus identity and configuration fingerprints match the committed comparison; semantic/legal-quality metrics remain null. Its output stays under ignored `.local/presentation/`, preserving the original report and its measured local latencies.

The edited README was rendered through GitHub's non-publishing Markdown API and inspected in an isolated unauthenticated browser using the actual GitHub page styling. The local rendered content was temporarily inserted only in that browser; relative image URLs were resolved to existing `main`-branch raw assets for preview. At 1440 and 390 CSS pixels, all four images loaded, body text was 16 px, and no page overflow was detected. Desktop/mobile previews and check output remain under ignored `.local/presentation/`. This validates a local GitHub-styled preview, not publication of the edited README or a novice-user study.

The stored **40 application-browser checks and 26 container smoke checks were not rerun in this documentation pass**. Their reports remain historical release evidence. Application behavior was preserved through unchanged source and the freshly run Python/frontend suites.

At the end of this presentation verification pass, Git HEAD and the index were unchanged: nothing had been staged, committed or pushed. These notes record that pre-publication state; a later authorized commit/push is a separate delivery step. GitHub description, topics, homepage and visibility were not modified. The [suggested metadata](github-metadata.md) awaits separate owner authorization. [Historical attribution](attribution.md) credits all four GitHub accounts identified from the predecessor's repository metadata and the owner's confirmed team size. No missing-member placeholder is needed. No live model/Pinecone calls, paid infrastructure or public application deployment were used.
