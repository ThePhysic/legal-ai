# Shared API contract (v1)

Base backend `http://127.0.0.1:8000`; browser uses same-origin `/api/v1/...` proxied by Next.js to backend `/v1/...`. JSON uses snake_case. Every protected operation derives workspace from HttpOnly session cookie or Bearer token; never accepts workspace/namespace from request data. Errors: `{detail: string}` with correct HTTP status; no tracebacks/private text.

## Identity / metadata

- `POST /v1/sessions` `{label?:string}` -> `{access_token:string, workspace_id:string, expires_at:string}` and HttpOnly cookie. Creates a NEW isolated local-demo workspace. No selecting another workspace. 201.
- `GET /v1/session` -> `{workspace_id:string, label:string, mode:'offline', provider_status: object}`. 401 when absent/expired.
- `DELETE /v1/session` -> 204; revoke token/cookie.
- `GET /v1/corpus` -> `{sources: Source[], coverage: string[], mode:'offline', limitations:string[]}`. Public-safe metadata, no private records.

## Passage / source / answer types

`Source`: `{source_id,title,publisher,url,source_type,jurisdiction,version,content_hash,captured_at,effective_from:null|string,effective_to:null|string,rights_basis,scope:'public'|'private'}`.

`Passage`: `{passage_id,source_id,version,locator,text,score:number,source:Source}`. Auth applies to full passage/source text. Scores are retrieval scores, not correctness probabilities.

`ResearchRequest`: `{question:string,jurisdiction:'US-CA'|string,applicable_on:null|string,source_scope:'public'|'private',document_id?:string,configuration:'lexical'|'dense'|'hybrid'|'rerank',top_k?:number}`. Optional fields default to public/lexical/5, date null. Question 1..2000 chars, top_k 1..10. Reject unknown fields that could spoof identity.

`SearchResponse`: `{run_id,configuration,method,passages:Passage[],coverage_gaps:string[],trace:object,usage:object}`.

`ResearchResponse`: `{run_id,status:'answered'|'insufficient_evidence'|'unavailable',question,answer:string,claims:Claim[],passages:Passage[],coverage_gaps:string[],limitations:string[],method:string,configuration:string,usage:object}`.

`Claim`: `{claim_id,text,passage_ids:string[],source_ids:string[],support_status:'verbatim_quote'|'not_assessed',identity_validated:boolean}`. Identity validation is not semantic certification.

- `POST /v1/search` ResearchRequest -> SearchResponse.
- `POST /v1/research` ResearchRequest -> ResearchResponse.
- `GET /v1/sources/{source_id}` -> Source + `{passages:Passage[]}`; workspace authorization for private IDs.
- `GET /v1/runs/{run_id}` -> authorized search/research trace + config/usage, no unrelated private data.

## Documents

- `GET /v1/documents` -> `{documents:Document[]}`.
- `POST /v1/documents` multipart `file` (.pdf/.docx/.txt/.md), optional `replace_document_id` -> Document (201); actual content validated. Limit 10 MB plus parser/decompression/text caps.
- `GET /v1/documents/{id}` -> Document + `{sections:[{locator,title,text}],passages:Passage[]}` (only if authorized/available).
- `POST /v1/documents/{id}/retry` -> Document, idempotent safe recovery.
- `GET /v1/documents/{id}/download` -> owned original file.
- `DELETE /v1/documents/{id}` -> `{document_id,status:'deleted'|'deletion_pending'}`; revoke immediately and reconcile.
- `POST /v1/documents/{id}/analysis` `{question?:string,locator?:string}` -> `{document_id,summary:string,findings:[{kind:'contract_text'|'document_fact'|'consideration'|'evidence_gap',title,text,locator,passage_ids:string[],verified:boolean}],answer:ResearchResponse|null,comparison:{passages:Passage[],limitations:string[]},method:string,limitations:string[]}`.

`Document`: `{document_id,filename,media_type,status:'uploaded'|'extracting'|'chunking'|'indexing'|'verifying'|'ready'|'failed'|'deleted'|'deletion_pending',version,content_hash,created_at,section_count,passage_count,error:string|null,processing:object}`. Actual API may process synchronously with a durable lifecycle; intermediate/failure states and retry remain persisted and inspectable.

## Evaluation (workspace scoped)

- `GET /v1/evaluations` -> `{runs: EvaluationRun[],datasets:[{id,title,revision,count,judgment_provenance}]}`.
- `POST /v1/evaluations` `{dataset_id:string,configurations:('lexical'|'dense'|'hybrid'|'rerank')[]}` -> EvaluationRun. Bounded public benchmark only; no arbitrary provider/config or private foreign data.
- `GET /v1/evaluations/{id}` -> EvaluationRun incl per-question traces and preserved configuration.

`EvaluationRun`: `{evaluation_id,dataset_id,dataset_revision,created_at,status,method,judgment_provenance,configurations:[{configuration,metrics:object,manifest:object,cases:object[]}],limitations:string[]}`. All figures actually measured; UI displays method/label provenance and no fabricated fixture claims. Unassessed human semantic metrics are null, not invented zero or perfect scores.

## Health

- `GET /health/live` -> `{status:'ok'}`.
- `GET /health/ready` -> readiness with explicit disabled/unconfigured live providers, offline database/storage status; no credentials.

Root coordinates schema changes. Backend agent may add necessary fields, but must message frontend/evaluation owners before changing established names or response nesting.
