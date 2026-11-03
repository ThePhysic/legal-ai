# Local API examples

Start the API, then run `uv run python examples/research.py` or `node examples/research.ts` from the project root. Both create a **new** local-demo workspace and use its opaque bearer token without printing it. No provider/API key is required and no model/Pinecone request is made.

`LEGAL_AI_BASE_URL` optionally points at your own configured application API. The examples inspect response status and coverage gaps before displaying exact source claims and versioned passage IDs. Do not interpret citation identity as independently reviewed legal correctness.

For Docker, set `LEGAL_AI_BASE_URL` to the published API URL (for example `http://127.0.0.1:8017`) and `LEGAL_AI_BROWSER_ORIGIN` to the configured frontend origin (`http://127.0.0.1:3017`). The Origin is required for a fresh session when the API observes a container-bridge client; native loopback SDK bootstrap can omit it. This does not select an existing workspace.

File uploads use multipart field `file` on `POST /v1/documents`; the server determines ownership from authentication. See the generated [OpenAPI contract](../docs/openapi.json) and [API notes](../docs/api-contract.md). Never send a workspace or vector namespace to select another user's records.
