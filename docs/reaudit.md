# Independent second audit — November 3, 2026

The user requested another check after the initial release. A fresh Astra medium backend audit, separate frontend and evaluation audits, controlled reproductions and fix reviews found the following issues. Earlier passing tests and approval did not cover these cases.

| Finding | Correction and regression evidence |
| --- | --- |
| Delayed document A response could display under B's filename | Removed duplicate detail reads; selection/abort guards protect completions and loading ownership. Deferred-response tests and a real delayed-HTTP browser replay verify B retains its own text. |
| Same-document detail failure had no reachable retry | A detail-specific **Try again** action retries the current selection once, with the same cancellation guards. |
| Quoted street addresses could hide foreign jurisdictions | Retrieval can omit street-name noise while scope checks retain city/state/country suffixes. Foreign postal locations abstain, including when the question also names California. |
| Analysis could falsely validate a literal split across chunks | Validated findings cite only passages containing their displayed text. A split literal remains visible with its section locator, empty passage references and unvalidated flags. |
| Public-source questions could retain pasted private text after deletion | All custom search/research history is private user content. Deletion/replacement purges owner-scoped history, including legacy public-marked records, while preserving frozen public evaluations. |
| NaN/noninteger budgets or mutated enable flags could bypass adapter guards | Call/token counters require nonnegative integers; amounts/prices must be finite; execution requires an exact boolean authorization. Mock tests prove failure before transport. |
| Failed Pinecone initialization left an unchecked cached connection | Publish the cache only after the pinned transport contract passes. Repeated failures remain closed and do not query. |
| Incomplete provider usage was counted as complete | Reports now distinguish complete, total and expected observations; unavailable usage stays unknown. |
| Sentinel-only recovery wrote a replacement key before failing | A remaining encryption sentinel blocks key generation when the original key is missing. |
| Capture tooling accepted changed PDFs with fixed reviewed page offsets | Pin the reviewed PDF hash, reject changed bytes before corpus mutation, and parse the exact bounded bytes that were hashed. |

The frontend pass also hardened cancelled research/analysis/retry completions, out-of-order listings, workspace unmounts, expired-session reconnects, saved traces and hidden-view autofocus. These are covered by component tests with deliberately delayed or abort-ignoring responses.

## Observed verification

- Complete offline Python suite: **392 passed**; Ruff clean. Two upstream deprecation warnings remain.
- Frontend: **30 tests passed**, formatting, type generation/typecheck and production build pass.
- Rebuilt PostgreSQL/API/production frontend: **26 smoke checks passed**.
- Real production browser suite: **40 checks passed**, including the new quoted-address and unvalidated-literal scenarios. An asynchronous deletion-focus check now waits for the actual frame-scheduled focus restoration before asserting it.
- The separate original race replay now requests A once and continues displaying B after the delayed response. Sanitized [before/after evidence](../artifacts/reaudit-race.json) records the observed difference. The fixtures are synthetic.
- Both reference clients returned actual source-linked results against the corrected container API.
- Benchmark `ef724df0fa894a02b6d8701b87b2d796` was regenerated and independently rechecked against current corpus, labels, code and configuration hashes. Retrieval scores are unchanged; each configuration has 56 complete of 56 total observations, zero observed provider usage and null semantic metrics. The dense recall failure remains recorded.

Independent **Astra medium** fix reviews are clean. The backend reviewer reran the original reproductions and 143 focused tests, then independently ran all 30 frontend tests and reviewed the integrated changes. A separate Astra reviewer cleared the provider/evaluation fixes after an additional exact-boolean execution guard was added. No remaining actionable complaints were reported in the reviewed offline scope.

This is an engineering audit with bounded tests and controlled failures. It does not prove absence of every possible bug or supply live Pinecone/model, independent legal-quality, production deployment or novice-user evidence. Those external gates remain deferred under the user's offline-only instruction.
