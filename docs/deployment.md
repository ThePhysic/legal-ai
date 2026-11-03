# Local and deployment recipes

The authorized release is local/offline. No cloud service or public website has been deployed. Provider execution remains disabled. The installed Docker daemon was started for verification: both images built, the PostgreSQL/API/production Next.js stack became healthy, and the real container smoke suite passed 26 checks. This is local container execution, not a public deployment.

## Local development

Use the README commands with SQLite, a durable encrypted runtime directory, API on loopback port 8000 and Next.js on loopback port 3000. Run bootstrap before migrations/starting the app. Keep `.env` and runtime state out of Git. The two local browser origins are explicit, and the frontend proxies `/api/v1/*` to the API. A different port/host requires coordinated Origin and rewrite configuration.

## Docker Compose

```sh
uv sync --frozen
uv run python scripts/bootstrap.py
docker compose config --quiet
docker compose up --build
```

Compose runs PostgreSQL, the offline API/worker and the standalone Next.js app. Published host ports bind loopback. API/frontend containers use non-root users. Private application payloads are encrypted with the generated key; the object/database volumes are durable. Compose is a local recipe, not an approved public production deployment.

API container startup runs Alembic before serving. Optional `LEGAL_AI_API_PORT` and `LEGAL_AI_FRONTEND_PORT` select alternate loopback ports; the initial verification used 8017/3017 to avoid colliding with the native development stack. To reproduce its synthetic end-to-end test: `uv run python scripts/container_smoke.py --app-url http://127.0.0.1:3017 --api-url http://127.0.0.1:8017`. Session creation through a container bridge must supply the configured browser Origin (the smoke script does); origin-free SDK bootstrap is reserved for server-observed loopback clients.

Before a public deployment, configure HTTPS reverse proxy, production identity, secure cookies, explicit HTTPS origins/hosts, secret-managed key/passwords, database/storage encryption and backup retention, distributed limits, isolated parser workers and observability redaction. `LEGAL_AI_PRODUCTION=true` rejects insecure cookie/key/origin settings, but these checks alone do not establish a hardened production service.

Health endpoints are `/health/live` and `/health/ready`. Readiness distinguishes working offline storage from disabled live providers. Run migrations before exposing a configured database. Use a release rollback and tested backup/key restore procedure; do not destroy volumes as a routine upgrade.

## Live integration approval checklist

Live execution is unavailable in this offline application mode. A separate reviewed enablement must specify the existing Pinecone host/index schema/metric/dimension, embedding/model versions and generation schema, server-derived namespaces/filters, source rights, provider choices, maximum calls/input/output tokens/latency/retries, estimated spend and observed-usage stop controls. Revalidate current official SDK/provider/account constraints. Do not create an index as a side effect of a search request.

The prepared dense profile is cosine/1,536-dimensional `text-embedding-3-small`, with proposed structured generation through OpenAI Responses. The local hash-vector baseline is a different method and must never be inserted into a semantic index under the provider model's identity. Actual provider outages must be reported as unavailable, not silently answered by another method. Mock-transport tests do not satisfy the live search/model quality gates.
