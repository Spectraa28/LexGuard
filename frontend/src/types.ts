export type DocumentStatus = "UPLOADED" | "PARSED" | "EMBEDDED" | "EMBEDDING" | "COMPLETED" | "FAILED";

export interface DocumentRecord {
  id: string;
  name: string;
  status: DocumentStatus;
  created_at: string;
  updated_at: string | null;
  chunk_count: number;
  is_stuck: boolean;
}

export interface Observability {
  tenant_id: string;
  documents_by_status: Record<string, number>;
  ready_documents: number;
  stuck_documents: number;
  chunk_count: number;
  queue_depth: number | null;
  supervisor_age_seconds: number | null;
  searches: number;
  average_search_ms: number;
  captured_at: string;
}

export interface Health {
  status: "healthy" | "degraded";
  database: string;
  rabbitmq: string;
  pipeline: {
    stuck_documents: number | null;
    last_supervisor_sweep_unix: number | null;
    queue_depth: number | null;
  };
}

export interface SearchResult {
  document_id: string;
  content: string;
  score: number;
  page_number: number | null;
}

export interface ScenarioResult {
  scenario_id: string;
  outcome: "passed" | "warning";
  summary: string;
  evidence: Array<{ label: string; value: string | number | null; unit?: string; healthy: boolean }>;
  executed_at: string;
}

export interface UploadItem {
  key: string;
  file: File;
  progress: number;
  status: "queued" | "uploading" | DocumentStatus | "ERROR";
  documentId?: string;
  message?: string;
}
