# legal.ai frontend

Next.js / React / TypeScript frontend for the local legal research and document-review app. The cream-and-green interface calls the real local API for retrieval, parsing, questions and evaluation runs.

## Run locally

First complete the [root README quickstart](../README.md#run-locally): install Python dependencies, generate local configuration with `scripts/bootstrap.py`, apply Alembic database migrations and start the backend on `127.0.0.1:8000`. The frontend requires Node.js 22.13 or later; Node.js 24 is used by the container image. Run these commands from `frontend/` in a second terminal:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. **Home**, **Research** and **My documents** are the main navigation; expand **Developer tools** for **Evaluation lab** and **Project reference**. URL fragments `#home`, `#research`, `#documents`, `#evaluations` and `#reference` support direct navigation.

The browser checks its session and creates a new isolated workspace when no valid session exists. An HttpOnly cookie, which browser JavaScript cannot read, holds the session; no bearer token is stored in browser storage. This is a local demo identity model with no production single sign-on (SSO) or account recovery. On expiry, mounted workspace views are cleared. Reconnecting creates a new workspace and does not restore previous documents; expiry itself does not delete them.

To check the frontend and run a local production build, use a separate terminal in `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run test
npm.cmd run format:check
npm.cmd run build
npm.cmd run start
```

Stop the development server before `npm.cmd run start` so both do not compete for port 3000. On shells that do not need the Windows `.cmd` suffix, use `npm`.

Dependencies are pinned in the committed `package-lock.json`. The UI requires no external fonts, images, analytics or model/provider requests. Clicking an original-source link opens the publisher website.

## Backend proxy and containers

Browser requests use `/api/v1/*` on the app's own origin (scheme, hostname and port); Next.js rewrites them to backend `/v1/*`. Set `API_BASE_URL` in the frontend shell before `npm run dev` or **before the production build** when overriding the default `http://127.0.0.1:8000`. Next.js embeds rewrite destinations during the build; a runtime-only change does not update them. For example, an API running on an alternate loopback port can be selected in PowerShell with `$env:API_BASE_URL = "http://127.0.0.1:8017"` before starting or building the frontend. Port 8017 is an optional example, not the default.

The build produces `.next/standalone/server.js`. A standalone deployment must also copy `.next/static` to `.next/standalone/.next/static` and `public` to `.next/standalone/public`, as [the frontend Dockerfile](../infrastructure/Dockerfile.frontend) does. The image builds its rewrite against the internal address `http://api:8000`. It sets `HOSTNAME=0.0.0.0` inside the container; normal development/start scripts bind loopback. Backend `LEGAL_AI_ALLOWED_ORIGINS` must match the browser origin, including its port. See [local Compose setup and alternate ports](../docs/deployment.md#docker-compose).

## Evidence and limitations

Research submits free-form questions; starter questions are editable prompts. The short answer is the first exact source sentence, or a clearly shortened exact excerpt, followed by full supporting claims. Offline extraction quotes retrieved text without a language model. Source and passage counts come from returned evidence. Capture dates do not establish legal effective dates, and a citation identity check confirms quote/source matching rather than independently assessing meaning. An evidence gap leads to abstention (declining to answer from insufficient support); a network or API failure instead shows a connection/error state with retry.

**My documents** sends actual files for parsing: PDF, DOCX, UTF-8 text and Markdown, up to 10 MB. Backend caps also bound pages, expanded archive/stream size, extracted text and parsing time. Scanned PDFs need optical character recognition (OCR), which is unavailable; encrypted and unsafe files are rejected. Start with the fictional [sample lease](../samples/example-lease.txt), then inspect sections, literal findings, rule-based considerations, document questions and public-source comparisons.

A ready replacement removes the previous current version from search. Replacement and deletion purge retained private questions/answers and analyses, and conservatively remove **all saved custom research/search history in that workspace**, including questions using public sources. Deletion immediately revokes document access. Frozen public evaluation reports remain. The UI distinguishes pending file cleanup from completed deletion. See [storage and retention limits](../docs/security.md).

**Evaluation lab** displays saved API measurements, label provenance, missing values, reproducibility settings and preserved failure cases. The local hash-vector baseline deterministically maps text into numbers; it is not trained semantic retrieval or live Pinecone. Model and Pinecone calls remain disabled. See the [walkthrough](../docs/walkthrough.md) for the full path through the app.

The interaction suite covers free-form research, evidence counts and unknown dates, network errors versus evidence gaps, cancellation, private session creation, actual sample File upload, document text, failed processing retry, and confirmation/pending deletion. Integrated browser checks and subjective novice-user research are separate gates. Native dialog keyboard focus, visible focus, status/error live regions, reduced motion and responsive layouts are implemented; this is not a claim of a full independent accessibility audit.

## Real browser acceptance checks

From the repository root, run `node scripts/browser-check.mjs` while the web/API are running. Optional environment variables: `LEGAL_AI_BASE_URL` (default `http://127.0.0.1:3000`), `LEGAL_AI_API_URL` (default `http://127.0.0.1:8000`), and `LEGAL_AI_BROWSER_PATH` (override the full Chrome, Edge, or Chromium executable path on Windows, macOS, or Linux). Without an override, installed browsers are detected from standard platform locations and the local Playwright cache. `LEGAL_AI_WEB_URL` is also supported as a base URL alias. The script drives the browser through the Chrome DevTools Protocol (CDP) over Node WebSocket, waits for local readiness, sends the correct `Origin` header on SDK requests, and keeps bearer tokens in memory.

`LEGAL_AI_CDP_PORT` selects another debug port and a matching ignored profile directory, so independent runs can use separate browser instances. Chromium sandbox disabling is enabled only on Linux with `CI=true`/`CI=1`, or with explicit `LEGAL_AI_BROWSER_NO_SANDBOX=true`/`1`; normal local Windows runs keep the sandbox.

Safe synthetic screenshots and measured results are written to `artifacts/browser`; the browser profile is ignored under `.local`. The suite performs actual API/UI research, document and evaluation flows, separate-session authorization checks, local transport interruption/retry, cancellation, source focus, modal keyboard behavior, labels, and responsive layouts. Native reduced-motion preference is enabled during rapid CDP pointer actions for stable hit targets. It checks key body/primary-button contrast pairs, not every color combination. The 720 CSS pixel reflow check represents 200% zoom on a 1440 CSS pixel viewport; it does not emulate native browser zoom. Invalid-file retry remains a failure as expected; successful interrupted-job recovery is verified by backend tests.

Committed screenshots and reports are historical evidence. See the [verification record](../docs/verification.md) for recorded results; this documentation does not claim a fresh browser run or a public application deployment.
