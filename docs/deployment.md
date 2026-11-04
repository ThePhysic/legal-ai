# Local setup and deployment preparation

The application runs locally and offline; no cloud service or public website deployment is claimed. Provider execution is disabled. A public GitHub repository makes the source available, but does not host the running application.

## Local development

Follow the [root README quickstart](../README.md#run-locally) for Python, Node.js and dependency requirements and the full two-terminal commands. The native stack uses SQLite and these default addresses:

| Component        | Default address         |
| ---------------- | ----------------------- |
| Next.js frontend | `http://127.0.0.1:3000` |
| FastAPI backend  | `http://127.0.0.1:8000` |

Run `uv run python scripts/bootstrap.py` from the repository root before migrations or startup. It generates an ignored `.env` and a durable encryption key; an existing `.env` is preserved. Use `uv run --env-file .env` for the Alembic migration and API commands so the same configuration is loaded. The default SQLite database, encrypted objects and key live under `.runtime/`. Preserve the original key for restore; changing it makes existing encrypted content unreadable.

The frontend proxies browser requests from `/api/v1/*` to backend `/v1/*`, keeping browser traffic on the app's origin (scheme, hostname and port). `API_BASE_URL` defaults to `http://127.0.0.1:8000`; set it in the frontend shell before development startup or **before a production build** to change the destination. Next.js records rewrite destinations during the build, so a runtime-only override does not update an existing build. The backend allowlist defaults to the `localhost:3000` and `127.0.0.1:3000` HTTP origins. A different browser port/host also requires updating `LEGAL_AI_ALLOWED_ORIGINS`; a different backend address requires the matching frontend rewrite. See the [frontend instructions](../frontend/README.md#backend-proxy-and-containers).

## Docker Compose

Run from the repository root with Docker and Docker Compose available:

```powershell
uv sync --frozen
uv run python scripts/bootstrap.py
docker compose config --quiet
docker compose up --build
```

Open `http://127.0.0.1:3000`. Compose runs PostgreSQL, the offline API/worker and the standalone Next.js app. Published host ports bind loopback, so they are reachable only from the local machine. API/frontend containers use non-root users. Private application payloads use the generated encryption key; database and object volumes retain data across container restarts. The frontend image builds its rewrite with `API_BASE_URL=http://api:8000`, the API's internal Compose address.

API container startup applies Alembic database migrations before serving. `LEGAL_AI_API_PORT` and `LEGAL_AI_FRONTEND_PORT` optionally select alternate host ports; the Compose browser-origin allowlist follows the frontend port. The stored verification used **8017/3017** to avoid a native-stack collision. Those are historical test ports, not defaults. To select them in PowerShell, set the variables before starting Compose:

```powershell
$env:LEGAL_AI_API_PORT = "8017"
$env:LEGAL_AI_FRONTEND_PORT = "3017"
docker compose up --build
```

The synthetic container check accepts explicit URLs; for the default ports, run this in another repository-root terminal:

```powershell
uv run python scripts/container_smoke.py --app-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000 --output .local/container-smoke.json
```

Use matching `3017`/`8017` URLs when running the alternate-port stack. The script's own URL defaults match that historical run, so specify URLs for a new run. Its ignored `.local` output keeps a rerun separate from committed evidence. Session creation through a container bridge must supply the configured browser `Origin` header (the smoke script does); origin-free software development kit (SDK) bootstrap is reserved for clients the server observes on loopback.

Before a public application deployment, configure an HTTPS reverse proxy, production identity, secure cookies, explicit HTTPS origins/hosts, secret-managed keys/passwords, database/storage encryption and backup retention, distributed request limits, isolated parser workers and redacted operational logs. `LEGAL_AI_PRODUCTION=true` rejects insecure cookie/key/origin settings, but these checks alone do not establish a hardened production service.

Health endpoints are `/health/live` and `/health/ready`. Readiness distinguishes working offline storage from disabled live providers. Run migrations before exposing a configured database. Use a release rollback and tested backup/key restore procedure; do not destroy volumes as a routine upgrade.

The [security guide](security.md) explains local session expiry, document deletion, saved-history purging and backup retention limits. The current session mechanism has no production identity recovery; expired workspaces need an operator retention policy.

## Recorded local verification

The [verification record](verification.md) reports 392 Python tests, 30 frontend tests, 40 browser checks and 26 container smoke checks for the stored offline release. The [container report](../artifacts/container-smoke.json) records a local PostgreSQL/API/production Next.js run at `3017`/`8017`. These counts are historical evidence, not a claim that this documentation edit reran the suites or deployed a public service.

## Deferred live integration

Live execution is unavailable in this application mode. A separately reviewed enablement must specify the existing Pinecone index and its vector format, model versions and structured answer format, server-derived workspace isolation, source rights, provider choices, call/token/time/retry limits, estimated spend and observed-usage stop controls. Revalidate current official SDK/provider/account constraints. Searching must not create an index as a side effect.

The prepared dense profile uses `text-embedding-3-small` with 1,536 numeric dimensions and cosine similarity, with proposed structured generation through OpenAI Responses. The local hash-vector baseline deterministically maps text to numbers; it is not a trained semantic embedding model or a Pinecone search. Offline answers quote retrieved text without a language model. A connection/provider failure must remain distinct from insufficient evidence, and intercepted test requests do not establish live search or model quality.
