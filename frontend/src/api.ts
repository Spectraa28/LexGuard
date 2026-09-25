import type { DocumentRecord, Health, Observability, ScenarioResult, SearchResult } from "./types";

const RETRIEVAL = "/retrieval";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  return body as T;
}

export async function getHealth(): Promise<Health> {
  const response = await fetch(`${RETRIEVAL}/health`);
  const body = await response.json();
  return body as Health;
}

export async function getDocuments(): Promise<DocumentRecord[]> {
  const response = await request<{ documents: DocumentRecord[] }>(`${RETRIEVAL}/demo/documents`);
  return response.documents;
}

export function getDocument(id: string): Promise<DocumentRecord> {
  return request<DocumentRecord>(`${RETRIEVAL}/demo/documents/${id}`);
}

export function getObservability(): Promise<Observability> {
  return request<Observability>(`${RETRIEVAL}/demo/observability`);
}

export async function searchDocuments(query: string): Promise<SearchResult[]> {
  const response = await request<{ results: SearchResult[] }>(`${RETRIEVAL}/demo/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit: 6 }),
  });
  return response.results;
}

export function runScenario(id: string): Promise<ScenarioResult> {
  return request<ScenarioResult>(`${RETRIEVAL}/demo/scenarios/${id}`, { method: "POST" });
}

export function uploadDocument(file: File, onProgress: (progress: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/ingestion/api/v1/documents");
    xhr.setRequestHeader("X-Tenant-ID", "demo");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      try {
        const payload = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(payload.documentId);
        else reject(new Error(payload.message || payload.detail || "Upload failed"));
      } catch {
        reject(new Error("The ingestion service returned an invalid response"));
      }
    };
    xhr.onerror = () => reject(new Error("Could not reach the ingestion service"));
    xhr.send(body);
  });
}
