# Security, retention and local operational boundaries

## Access model

`POST /v1/sessions` creates a fresh workspace with an opaque randomly generated token; it never selects an existing workspace. Tokens are hashed in the database and provided via an HttpOnly/SameSite cookie or a caller-held SDK bearer token. Conflicting credentials fail. Session expiry/revocation removes access; this demo has no identity recovery or workspace transfer. A production release must integrate authenticated identity/recovery rather than exposing anonymous session creation publicly.

All private actions derive ownership on the server, including nested source/passage IDs, downloads, retry/replacement/deletion, analysis, traces and evaluation results. Cross-workspace IDs fail without returning foreign content. Public benchmark cases contain no private documents. A private vector namespace must derive from authenticated ownership, never a caller-supplied filter. The current application is locked offline; provider contracts are separately transport-tested.

Browser writes require an allowlisted Origin when authenticated by cookie. Any supplied unexpected Origin is rejected, including bootstrap. Origin-free bootstrap is only for recognized loopback SDK/test clients and always creates a new workspace. SDK requests should use Bearer tokens and omit browser cookies. Proxy and local hosts/origins must be configured consistently; no wildcard CORS is enabled. Do not log authorization/cookie headers or export unredacted private request/answer payloads.

## Stored data

Private file bytes, document payloads/sections/passages and run/analysis text are authenticated ciphertext. Safe IDs, version/content hashes, timestamps, status and session hashes remain database metadata. Public corpus snapshots are unencrypted public statutory text. Encryption does not prevent an authorized running process or a compromised OS administrator from reading unlocked content.

The ignored runtime key `.runtime/.encryption.key` survives restart. An operator may supply `LEGAL_AI_ENCRYPTION_KEY`; existing data must use the same key. A sentinel detects mismatch. Missing keys for existing encrypted state fail closed; restore the key rather than generating a replacement. The bootstrap helper preserves existing keys. Rotation requires an explicit offline decrypt/re-encrypt migration, backup and validation; automatic rotation is not implemented. Protect the local directory with OS access permissions, and use secret-managed production keys and encrypted backups/storage.

Deletion revokes document search/access immediately and removes retained private run/analysis text, then removes stored original objects/chunks. Failed cleanup stays deletion-pending and is retryable; it must never restore visibility. Local demo backups are operator controlled: document deletion cannot erase arbitrary OS backups, clipboard content or files a user downloaded. Production must disclose backup retention and exceptions before confirmation. Session expiry does not itself erase documents; an operator retention procedure is needed for abandoned workspaces.

Custom questions and search/research history are private user content even when their evidence comes from public statutes. Document deletion or replacement conservatively purges all saved custom search/research history in that workspace, including history from earlier releases that classified public-source questions differently. Frozen public evaluation reports remain available. This policy concerns saved server records; it cannot erase text copied, downloaded or independently retained by the browser or user.

## Parsing and resource isolation

Allowed inputs are capped PDF, DOCX, text and Markdown. Validate signatures and UTF-8; reject encrypted PDFs, scanned/no-text files, PDF active/embedded content, unsafe OOXML relationships/entities/archive paths and excessive compressed expansion. Extraction runs in a separate process with a kill timeout and output caps. This reduces risk but is not a hardened parser sandbox; production should use isolated containers with CPU/memory/filesystem/network restrictions and patched parsing libraries.

Source/document text is untrusted data. The application does not execute uploaded code, embedded links or source instructions, and React escapes rendered text. Extractive quotes cannot change authorization or create tools. Citation identity, legal applicability and semantic support are distinct. Provider output must pass structured schema and source/version/quote checks before exposure; no provider-memory fallback is permitted.

Literal analysis findings cite only passages that actually contain the displayed text and match its document/version. A value split across passages remains visible with a section locator, empty passage references and unvalidated identity flags. The interface distinguishes this section text from a validated passage quote and from a rule-based consideration.

## Operational limits

This is a single-process local demo with in-memory rate counters and a local durable ingestion path. Multi-worker distributed rate enforcement, production SSO, centralized secrets/rotation, hardened parser workers, external backup retention and live observability integrations are deployment gates, not completed claims. Access logging is disabled in the documented launch command; application diagnostics expose safe IDs/timing/configuration rather than private text or tokens.

Inspect [design.md](design.md) for exact caps and acceptance thresholds. Use the tracked-file scanner and dependency audits as practical gates, not as guarantees that all secret formats or unknown vulnerabilities have been found.

The full-history Gitleaks scan has one narrowly documented historical false-positive exclusion: an empty `.env.example` API-key assignment was matched across a newline into the following dimension-variable name. No key was present. `.gitleaksignore` names only that exact commit/file/rule/line fingerprint; current placeholders are quoted, and no directory-wide or rule-wide exclusion is used.
