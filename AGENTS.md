# Project implementation rules

This is a fresh independent project. Do not copy implementation code, prompts, assets, credentials or databases from earlier legal.ai/Cal Hacks repositories. The approved local UX proposal is a design reference, not a backend implementation.

User scope: implement the full local product and prepare provider/deployment integration, but **offline only for now**. No live Pinecone/LLM requests, paid calls, cloud provisioning or deployment. Creating a private ThePhysic/legal-ai GitHub repository and pushing the finished reviewed project is explicitly authorized.

Use parallel agents with disjoint file ownership. Root owns Git, shared contracts, corpus, documentation, infrastructure, integration checks and publication. Agents must not commit or push independently. Raise contract changes before altering them.

Use Astra (`gpt-6-astra`, medium reasoning) for independent milestone/final adversarial review. Resolve valid complaints and rereview until clean. Report offline measurements, synthetic tests and unexecuted live gates distinctly. Never invent performance, source applicability, human review or security evidence.

Security: authenticated server-derived workspace scope; no client-selected namespaces; private storage paths derived from stable IDs; safe capped parsing; untrusted text is data; redacted diagnostics. No tracked runtime data, secrets, private uploads, local browser profiles or dependency directories.

The frontend preserves the cream/green approved UX, first-visit two-task choice, customer/developer separation, short answer/support/limits/source hierarchy, readable typography, keyboard focus and accessible feedback. Replace scripted proposal outcomes with actual backend behavior; label deterministic extraction and local retrieval methods honestly.

Use meaningful tests for authorization, parsing, citation identity, retrieval/evaluation correctness, failure recovery and integrated user flows. Required acceptance and API contracts live in docs/design.md and docs/api-contract.md.
