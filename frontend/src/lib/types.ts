export interface Hospital {
  id: string;
  name: string;
  code: string;
}

export type PaStatus =
  | "draft"
  | "pending"
  | "needs_info"
  | "approved"
  | "denied"
  | "completed"
  | "cancelled";

export interface PaCase {
  id: string;
  request_number: string;
  patient: string;
  payer: string;
  status: PaStatus;
  created_at: string;
  clinical_notes: string;
}

export interface Citation {
  source_doc: string;
  chunk: number | null;
  quote: string;
}

export interface ProposedCode {
  code: string;
  description: string;
  code_system: "ICD10" | "CPT" | "HCPCS" | "OTHER";
  confidence: number;
  grounded: boolean;
  citations: Citation[];
}

export interface ProposedCodes {
  codes: ProposedCode[];
  rationale: string;
  grounded: boolean;
  fallback_used: boolean;
  notes: string;
}

export interface ExtractResult {
  status: string; // "pending_review"
  proposed: ProposedCodes;
  summary?: string;
}

export interface ReviewResult {
  status: string; // "reviewed:approve" | ...
  final_codes: ProposedCode[];
  decision: string;
}

export interface AskSource {
  tool: string;
  detail: string;
  source_doc?: string;
  chunk?: number | null;
}

export interface AskResult {
  answer: string;
  status: string;
  sources: AskSource[];
  grounded: boolean;
}
