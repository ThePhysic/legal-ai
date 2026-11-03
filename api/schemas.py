from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SessionRequest(StrictModel):
    label: str = Field(default="Local workspace", min_length=1, max_length=80)


class ResearchRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    jurisdiction: str = Field(default="US-CA", min_length=1, max_length=40)
    applicable_on: date | None = None
    source_scope: Literal["public", "private"] = "public"
    document_id: str | None = Field(default=None, max_length=64)
    configuration: Literal["lexical", "dense", "hybrid", "rerank"] = "lexical"
    top_k: int = Field(default=5, ge=1, le=10)


class AnalysisRequest(StrictModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    locator: str | None = Field(default=None, min_length=1, max_length=120)


class EvaluationRequest(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=80)
    configurations: list[Literal["lexical", "dense", "hybrid", "rerank"]] = Field(min_length=1, max_length=4)


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Source(OutputModel):
    source_id: str
    title: str
    publisher: str
    url: str
    source_type: str
    jurisdiction: str
    version: str
    content_hash: str
    captured_at: str
    effective_from: str | None
    effective_to: str | None
    rights_basis: str
    scope: Literal["public", "private"]


class Passage(OutputModel):
    passage_id: str
    source_id: str
    version: str
    locator: str
    text: str
    score: float
    source: Source


class SourceResponse(Source):
    passages: list[Passage]


class CorpusResponse(OutputModel):
    sources: list[Source]
    coverage: list[str]
    mode: Literal["offline"]
    limitations: list[str]


class Claim(OutputModel):
    claim_id: str
    text: str
    passage_ids: list[str]
    source_ids: list[str]
    support_status: Literal["verbatim_quote", "not_assessed"]
    identity_validated: bool = Field(description="Source/version/quotation identity only, not semantic verification")


class SearchResponse(OutputModel):
    run_id: str
    configuration: str
    method: str
    passages: list[Passage]
    coverage_gaps: list[str]
    trace: dict[str, Any]
    usage: dict[str, Any]


class ResearchResponse(OutputModel):
    run_id: str
    status: Literal["answered", "insufficient_evidence", "unavailable"]
    question: str
    answer: str
    claims: list[Claim]
    passages: list[Passage]
    coverage_gaps: list[str]
    limitations: list[str]
    method: str
    configuration: str
    usage: dict[str, Any]


class DocumentResponse(OutputModel):
    document_id: str
    filename: str
    media_type: str
    status: Literal["uploaded", "extracting", "chunking", "indexing", "verifying", "ready", "failed", "deleted", "deletion_pending"]
    version: str
    content_hash: str
    created_at: str
    section_count: int
    passage_count: int
    error: str | None
    processing: dict[str, Any]


class Section(OutputModel):
    locator: str
    title: str
    text: str


class DocumentDetail(DocumentResponse):
    sections: list[Section]
    passages: list[Passage]


class DocumentListing(OutputModel):
    documents: list[DocumentResponse]


class Finding(OutputModel):
    kind: Literal["contract_text", "document_fact", "consideration", "evidence_gap"]
    title: str
    text: str
    locator: str | None
    passage_ids: list[str]
    verified: bool = Field(description="Compatibility name: literal identity/text matching only")
    identity_validated: bool
    support_status: Literal["verbatim_quote", "not_assessed"]


class Comparison(OutputModel):
    passages: list[Passage]
    limitations: list[str]


class AnalysisResponse(OutputModel):
    document_id: str
    summary: str
    findings: list[Finding]
    answer: ResearchResponse | None
    comparison: Comparison
    method: str
    limitations: list[str]


class EvaluationConfiguration(OutputModel):
    configuration: str
    metrics: dict[str, Any]
    manifest: dict[str, Any]
    cases: list[dict[str, Any]]


class EvaluationRun(OutputModel):
    evaluation_id: str
    dataset_id: str
    dataset_revision: str
    created_at: str
    status: str
    method: str
    judgment_provenance: str
    configurations: list[EvaluationConfiguration]
    limitations: list[str]


class Dataset(OutputModel):
    id: str
    title: str
    revision: str
    count: int
    judgment_provenance: str


class EvaluationListing(OutputModel):
    runs: list[EvaluationRun]
    datasets: list[Dataset]
