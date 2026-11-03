export type Configuration = "lexical" | "dense" | "hybrid" | "rerank";
export interface Source {
  source_id: string;
  title: string;
  publisher: string;
  url: string;
  source_type: string;
  jurisdiction: string;
  version: string;
  content_hash: string;
  captured_at: string;
  effective_from: string | null;
  effective_to: string | null;
  rights_basis: string;
  scope: "public" | "private";
}
export interface Passage {
  passage_id: string;
  source_id: string;
  version: string;
  locator: string;
  text: string;
  score: number;
  source: Source;
}
export interface Claim {
  claim_id: string;
  text: string;
  passage_ids: string[];
  source_ids: string[];
  support_status: "verbatim_quote" | "not_assessed";
  identity_validated: boolean;
}
export interface ResearchRequest {
  question: string;
  jurisdiction: string;
  applicable_on: string | null;
  source_scope: "public" | "private";
  document_id?: string;
  configuration: Configuration;
  top_k?: number;
}
export interface ResearchResponse {
  run_id: string;
  status: "answered" | "insufficient_evidence" | "unavailable";
  question: string;
  answer: string;
  claims: Claim[];
  passages: Passage[];
  coverage_gaps: string[];
  limitations: string[];
  method: string;
  configuration: string;
  usage: Record<string, unknown>;
}
export interface Session {
  workspace_id: string;
  label: string;
  mode: "offline";
  provider_status: Record<string, unknown>;
}
export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "chunking"
  | "indexing"
  | "verifying"
  | "ready"
  | "failed"
  | "deleted"
  | "deletion_pending";
export interface LegalDocument {
  document_id: string;
  filename: string;
  media_type: string;
  status: DocumentStatus;
  version: string;
  content_hash: string;
  created_at: string;
  section_count: number;
  passage_count: number;
  error: string | null;
  processing: Record<string, unknown>;
}
export interface DocumentDetail extends LegalDocument {
  sections: { locator: string; title: string; text: string }[];
  passages: Passage[];
}
export interface DocumentAnalysis {
  document_id: string;
  summary: string;
  findings: {
    kind: "contract_text" | "document_fact" | "consideration" | "evidence_gap";
    title: string;
    text: string;
    locator: string;
    passage_ids: string[];
    verified: boolean;
  }[];
  answer: ResearchResponse | null;
  comparison: { passages: Passage[]; limitations: string[] };
  method: string;
  limitations: string[];
}
export interface Dataset {
  id: string;
  title: string;
  revision: string;
  count: number;
  judgment_provenance: string;
}
export interface EvaluationConfiguration {
  configuration: string;
  metrics: Record<string, unknown>;
  manifest: Record<string, unknown>;
  cases: Record<string, unknown>[];
}
export interface EvaluationRun {
  evaluation_id: string;
  dataset_id: string;
  dataset_revision: string;
  created_at: string;
  status: string;
  method: string;
  judgment_provenance: string;
  configurations: EvaluationConfiguration[];
  limitations: string[];
}
