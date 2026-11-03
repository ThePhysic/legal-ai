# legal.ai frontend

Independent Next.js / React / TypeScript implementation of the local product. The approved cream-and-green proposal informed the visual hierarchy and behavior; this app calls the actual local API.

## Run locally

Requires Node.js 22.13 or later and the backend on `127.0.0.1:8000`.

```powershell
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. Hash routes `#research`, `#documents`, `#evaluations` and `#reference` support direct navigation. The browser checks its HttpOnly session and creates a new isolated workspace only if there is no valid session. It does not store a bearer token in browser storage or choose another workspace.

```powershell
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run start
```

All dependencies are pinned; `package-lock.json` is committed. No external fonts, images, analytics or provider requests are required by the UI. Clicking an original-source link opens the publisher website deliberately.

## Backend proxy and containers

Browser requests use same-origin `/api/v1/*`; Next rewrites them to backend `/v1/*`. Set `API_BASE_URL` before `npm run dev` or **before the production build** when overriding the default `http://127.0.0.1:8000`. Next embeds rewrite destinations during the build; a runtime-only change does not update them.

The build produces `.next/standalone/server.js`. For the standalone container, copy `.next/static` to `.next/standalone/.next/static` and `public` to `.next/standalone/public`, following the root Dockerfile. Bind `HOSTNAME=0.0.0.0` only inside the container; normal dev/start scripts bind loopback. Backend Origin settings must match the browser origin.

## Evidence and limitations

Research submits free-form questions. Starter questions are editable prompts, not scripted outcomes. Source and passage counts come from the returned evidence; source links alone do not count as support. Capture dates and unknown effective dates remain separate. Citation identity is not independent semantic assessment.

Document review uses real multipart uploads (including the synthetic sample), parser sections, analysis/Q&A, source comparison, recovery and deletion endpoints. Confirmation reports pending cleanup separately from completed deletion. Replacement copy only says the earlier version is no longer current when the new document is ready. Expired sessions clear mounted workspace views; reconnecting a new workspace remounts state.

Evaluation displays saved API measurements, judgment provenance, missing values, manifests and preserved cases. No fixture metrics are rendered. Offline extraction and the deterministic local vector baseline are distinct from live models and Pinecone, which remain disabled.

The interaction suite covers free-form research, evidence counts and unknown dates, network errors versus evidence gaps, cancellation, private session creation, actual sample File upload, document text, failed processing retry, and confirmation/pending deletion. Integrated browser checks and subjective novice-user research are separate gates. Native dialog keyboard focus, visible focus, status/error live regions, reduced motion and responsive layouts are implemented; this is not a claim of a full independent accessibility audit.

The customer takeaway shows the first exact source sentence (or a clearly shortened exact excerpt), not an invented synthesis of retrieved passages. Full claims appear once in the support section; the raw API response remains under advanced details.

## Real browser acceptance checks

From the repository root, run `node scripts/browser-check.mjs` while the web/API are running. Optional environment variables: `LEGAL_AI_BASE_URL` (default `http://127.0.0.1:3000`), `LEGAL_AI_API_URL` (default `http://127.0.0.1:8000`), and `LEGAL_AI_BROWSER_PATH` (override the full Chrome, Edge, or Chromium executable path on Windows, macOS, or Linux). Without an override, installed browsers are detected from standard platform locations and the local Playwright cache. `LEGAL_AI_WEB_URL` is also supported as a base URL alias. The script uses native Node WebSocket/CDP, waits for local readiness, sends the correct Origin on SDK requests, and keeps bearer tokens in memory.

`LEGAL_AI_CDP_PORT` selects another debug port and a matching ignored profile directory, so independent runs can use separate browser instances. Chromium sandbox disabling is enabled only on Linux with `CI=true`/`CI=1`, or with explicit `LEGAL_AI_BROWSER_NO_SANDBOX=true`/`1`; normal local Windows runs keep the sandbox.

Safe synthetic screenshots and measured results are written to `artifacts/browser`; the browser profile is ignored under `.local`. The suite performs actual API/UI research, document and evaluation flows, separate-session authorization checks, local transport interruption/retry, cancellation, source focus, modal keyboard behavior, labels, and responsive layouts. Native reduced-motion preference is enabled during rapid CDP pointer actions for stable hit targets. It checks key body/primary-button contrast pairs, not every color combination. The 720 CSS pixel reflow check represents 200% zoom on a 1440 CSS pixel viewport; it does not emulate native browser zoom. Invalid-file retry remains a failure as expected; successful interrupted-job recovery is verified by backend tests.
