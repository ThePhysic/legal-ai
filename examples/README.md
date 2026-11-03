# Local API examples

Start the API, then run `uv run python examples/research.py` or `node examples/research.ts` from the project root. Both create a **new** local-demo workspace and use its opaque bearer token without printing it. No provider/API key is required and no model/Pinecone request is made.

`LEGAL_AI_BASE_URL` optionally points at your own configured application API. The examples inspect response status and coverage gaps before displaying exact source claims and versioned passage IDs. Do not interpret citation identity as independently reviewed legal correctness.

File uploads use multipart field `file` on `POST /v1/documents`; the server determines ownership from authentication. See the generated [OpenAPI contract](../docs/openapi.json) and [API notes](../docs/api-contract.md). Never send a workspace or vector namespace to select another user's records.
