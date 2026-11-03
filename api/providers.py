"""Prepared adapters. The application never enables them in this offline release.

Pinecone 10.3.0 verified against the official SDK on 2026-11-03:
https://sdk.pinecone.io/python/reference/pinecone.html
https://sdk.pinecone.io/python/reference/sync-index.html
Dense vector index (dimension/metric), NOT a document-schema or integrated index.
No creation, host discovery or inference calls are made by this adapter.
"""

import hashlib
import math
import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from api.retrieval import validate_claims


class ProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PineconeProfile:
    host: str
    api_key: str = field(repr=False)
    dimension: int
    embedding_model: str
    embedding_revision: str
    metric: str = "cosine"
    schema_version: str = "legal-ai-v1"
    timeout: float = 5.0

    def validate(self):
        parsed = urlsplit(self.host)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".pinecone.io"):
            raise ValueError("An explicit HTTPS Pinecone data-plane host is required.")
        if parsed.path not in ("", "/") or parsed.query or parsed.username:
            raise ValueError("Invalid data-plane host.")
        if not self.api_key or self.dimension < 1 or not self.embedding_model or not self.embedding_revision:
            raise ValueError("A complete pinned embedding/index profile is required.")
        if self.metric not in ("cosine", "dotproduct", "euclidean") or not 0 < self.timeout <= 10:
            raise ValueError("Invalid index metric or request timeout.")


class ExistingPineconeAdapter:
    def __init__(self, profile: PineconeProfile, *, enabled: bool = False, call_budget: int = 0):
        profile.validate()
        self.profile = profile
        self.enabled = enabled
        self._index = None
        self._remaining_calls = call_budget
        self._budget_lock = threading.Lock()

    def _connection(self):
        if not self.enabled:
            raise ProviderUnavailable("Live Pinecone execution is disabled.")
        with self._budget_lock:
            if self._remaining_calls <= 0:
                raise ProviderUnavailable("Pinecone execution requires an explicit positive call budget.")
            self._remaining_calls -= 1
        if self._index is None:
            from pinecone import Pinecone, RetryConfig

            pc = Pinecone(api_key=self.profile.api_key, timeout=self.profile.timeout, retry_config=RetryConfig(max_retries=0))
            self._index = pc.index(host=self.profile.host)
            pc.close()
            # SDK 10.3.0 does not propagate the public control-plane retry_config
            # to pc.index(). Enforce zero data-plane retries in this pinned
            # compatibility seam, and fail closed if a future SDK changes it.
            transport = self._index._http._client._transport
            if not hasattr(transport, "_config"):
                raise ProviderUnavailable("Pinned Pinecone transport retry contract changed.")
            transport._config = RetryConfig(max_retries=0)
        return self._index

    @staticmethod
    def namespace(workspace_id: str | None):
        return "public-v1" if workspace_id is None else "private-" + hashlib.sha256(workspace_id.encode()).hexdigest()

    def _vector(self, vector):
        if len(vector) != self.profile.dimension or any(not math.isfinite(value) for value in vector):
            raise ValueError("Vector does not match the configured embedding dimension.")

    def query(self, vector, *, workspace_id, jurisdiction, allowed_passages, top_k=5, applicable_on=None):
        self._vector(vector)
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        constraints = [{"schema_version": {"$eq": self.profile.schema_version}},
                       {"jurisdiction": {"$eq": jurisdiction}}, {"current": {"$eq": True}},
                       {"scope": {"$eq": "public" if workspace_id is None else "private"}}]
        if applicable_on:
            ordinal = applicable_on.toordinal()
            constraints.extend([{"effective_from": {"$lte": ordinal}}, {"effective_to": {"$gte": ordinal}}])
        try:
            response = self._connection().query(vector=vector, top_k=top_k,
                namespace=self.namespace(workspace_id), filter={"$and": constraints},
                include_metadata=True, include_values=False, timeout=self.profile.timeout)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable("Pinecone query failed; no offline substitution was made.") from exc
        results = []
        for match in response.matches:
            canonical = allowed_passages.get(match.id)
            metadata = match.metadata or {}
            if not canonical or not math.isfinite(match.score) or any(metadata.get(key) != canonical[key] for key in ("source_id", "version")):
                raise ProviderUnavailable("Pinecone returned an unauthorized or stale source identity.")
            results.append({**canonical, "score": float(match.score)})
        return results

    def upsert(self, records, *, workspace_id):
        vectors = []
        for item in records:
            self._vector(item["values"])
            metadata = item["metadata"]
            if not all(metadata.get(key) for key in ("source_id", "version", "jurisdiction")):
                raise ValueError("Records require immutable source and version identity.")
            metadata = {**metadata, "schema_version": self.profile.schema_version,
                        "scope": "public" if workspace_id is None else "private"}
            vectors.append({"id": item["id"], "values": item["values"], "metadata": metadata})
        if len(vectors) > 100:
            raise ValueError("Upsert batch exceeds 100 records.")
        try:
            return self._connection().upsert(vectors=vectors, namespace=self.namespace(workspace_id), timeout=self.profile.timeout)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable("Pinecone indexing failed.") from exc

    def delete(self, passage_ids, *, workspace_id):
        if len(passage_ids) > 400:
            raise ValueError("Delete batch exceeds 400 identities.")
        try:
            return self._connection().delete(ids=passage_ids, namespace=self.namespace(workspace_id), timeout=self.profile.timeout)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable("Pinecone deletion failed; reconciliation is required.") from exc


class GroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    passage_ids: list[str] = Field(min_length=1, max_length=10)
    source_ids: list[str] = Field(min_length=1, max_length=10)
    support_status: str = "not_assessed"
    identity_validated: bool = False


class GroundedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(max_length=10000)
    claims: list[GroundedClaim] = Field(max_length=12)


class GroundedTransport(Protocol):
    def __call__(self, *, question: str, evidence: list[dict], output_schema: dict,
                 max_output_tokens: int, timeout: float) -> dict: ...


class GroundedLLMAdapter:
    """Structured bounded protocol; a provider transport must be explicitly supplied.

    Citation identity is checked locally. Semantic support remains not_assessed.
    This adapter is not registered as an executable application provider.
    """

    def __init__(self, transport: GroundedTransport | Callable, *, enabled=False):
        self.transport, self.enabled = transport, enabled

    def generate(self, question, passages):
        if not self.enabled:
            raise ProviderUnavailable("Live generation is disabled.")
        if len(question) > 2000 or sum(len(item["text"].encode()) for item in passages) > 4000:
            raise ValueError("Generation context exceeds the provider budget.")
        try:
            output = GroundedOutput.model_validate(self.transport(question=question, evidence=passages,
                output_schema=GroundedOutput.model_json_schema(), max_output_tokens=1000, timeout=10))
            claims = [claim.model_dump() for claim in output.claims]
            for claim in claims:
                claim["support_status"] = "not_assessed"
                claim["identity_validated"] = True
            if not validate_claims(claims, passages):
                raise ValueError("Invalid source/version citation identity")
            if output.answer.strip() and not claims:
                raise ValueError("An answer requires referenced claims")
            return {"answer": "\n\n".join(claim["text"] for claim in claims), "claims": claims,
                    "semantic_support": "not_assessed"}
        except Exception as exc:
            raise ProviderUnavailable("Grounded generation failed structured output or citation validation.") from exc
