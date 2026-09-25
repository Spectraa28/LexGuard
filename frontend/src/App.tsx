import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  FileSearch,
  Files,
  FileText,
  FlaskConical,
  HardDrive,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Server,
  Shield,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import * as api from "./api";
import type { DocumentRecord, DocumentStatus, Health, Observability, ScenarioResult, SearchResult, UploadItem } from "./types";

type View = "overview" | "documents" | "search" | "tests" | "architecture";
type DocumentFilter = "all" | "processing" | "completed" | "stuck" | "failed";

const processingStates: DocumentStatus[] = ["UPLOADED", "PARSED", "EMBEDDED", "EMBEDDING"];
const pipelineStates: DocumentStatus[] = ["UPLOADED", "PARSED", "EMBEDDED", "EMBEDDING", "COMPLETED"];

const navItems: Array<{ id: View; label: string; icon: typeof LayoutDashboard }> = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "documents", label: "Documents", icon: Files },
  { id: "search", label: "Search", icon: Search },
  { id: "tests", label: "System tests", icon: FlaskConical },
  { id: "architecture", label: "Architecture", icon: Network },
];

const scenarios = [
  { id: "pipeline", title: "Ingestion pipeline", description: "Queue connectivity, indexed output, and durable document state." },
  { id: "recovery", title: "Recovery supervisor", description: "Heartbeat freshness and documents outside the processing window." },
  { id: "isolation", title: "Tenant isolation", description: "Visibility of demo documents versus records outside the tenant boundary." },
  { id: "retrieval", title: "Retrieval readiness", description: "Completed documents and vector chunks available to semantic search." },
];

const architectureFlows = {
  ingestion: {
    label: "Ingestion",
    summary: "The write path accepts a PDF, commits durable metadata, and processes it asynchronously.",
    steps: [
      ["01", "Upload API", "Spring Boot validates the request and streams the file to R2."],
      ["02", "PostgreSQL outbox", "Document state and the processing event commit atomically."],
      ["03", "RabbitMQ", "The relay publishes with confirms; the worker consumes one job at a time."],
      ["04", "Embedding worker", "PDF text is chunked, encoded, and advanced through checkpoints."],
      ["05", "pgvector", "Page-aware chunks and 384-dimensional vectors become searchable."],
    ],
  },
  retrieval: {
    label: "Retrieval",
    summary: "The read path binds a tenant before ranking evidence from completed documents.",
    steps: [
      ["01", "Query API", "FastAPI validates the question and creates its embedding."],
      ["02", "Tenant scope", "The authenticated tenant identifier is bound directly into SQL."],
      ["03", "Vector ranking", "Cosine distance ranks current chunks from completed documents."],
      ["04", "Evidence response", "Every passage retains document, page, and similarity lineage."],
    ],
  },
  recovery: {
    label: "Recovery",
    summary: "The supervisor finds abandoned work and resumes it from the last safe checkpoint.",
    steps: [
      ["01", "Heartbeat sweep", "The supervisor scans intermediate states every sixty seconds."],
      ["02", "Stuck detection", "Rows beyond the timeout are locked with SKIP LOCKED."],
      ["03", "Staged rollback", "The document returns to the safest recoverable state."],
      ["04", "Requeue", "A new outbox event resumes processing without duplicate vectors."],
    ],
  },
} as const;

function relativeTime(value?: string | null) {
  if (!value) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function fileSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusTag({ status, stuck = false }: { status: string; stuck?: boolean }) {
  const label = stuck ? "Stuck" : status.toLowerCase().replace(/_/g, " ");
  const tone = stuck || status === "FAILED" || status === "degraded" || status === "warning"
    ? "negative"
    : status === "COMPLETED" || status === "healthy" || status === "passed"
      ? "positive"
      : "neutral";
  return <span className={`tag tag-${tone}`}><span />{label}</span>;
}

function PageHeader({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: React.ReactNode }) {
  return (
    <div className="page-header">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

function PipelineProgress({ status }: { status: DocumentStatus }) {
  const active = pipelineStates.indexOf(status);
  return <div className="pipeline-progress" aria-label={`Pipeline status: ${status}`}>{pipelineStates.map((step, index) => <span key={step} className={index <= active ? "complete" : ""} />)}</div>;
}

function DocumentTable({ documents, filter = "all", onFilter, compact = false }: { documents: DocumentRecord[]; filter?: DocumentFilter; onFilter?: (filter: DocumentFilter) => void; compact?: boolean }) {
  const visible = useMemo(() => documents.filter((document) => {
    if (filter === "processing") return processingStates.includes(document.status);
    if (filter === "completed") return document.status === "COMPLETED";
    if (filter === "stuck") return document.is_stuck;
    if (filter === "failed") return document.status === "FAILED";
    return true;
  }), [documents, filter]);

  return (
    <div className="table-section">
      {onFilter && <div className="segmented-control">{(["all", "processing", "completed", "stuck", "failed"] as DocumentFilter[]).map((item) => <button className={item === filter ? "active" : ""} onClick={() => onFilter(item)} key={item}>{item}</button>)}</div>}
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>Document</th><th>Status</th><th>Chunks</th><th>Last update</th><th>Progress</th></tr></thead>
          <tbody>
            {visible.slice(0, compact ? 6 : undefined).map((document) => (
              <tr key={document.id} className={document.is_stuck ? "attention-row" : ""}>
                <td><div className="document-cell"><span className="file-glyph"><FileText size={16} /></span><div><strong>{document.name}</strong><small>{document.id.slice(0, 8)}</small></div></div></td>
                <td><StatusTag status={document.status} stuck={document.is_stuck} /></td>
                <td>{document.chunk_count.toLocaleString()}</td>
                <td>{relativeTime(document.updated_at || document.created_at)}</td>
                <td><PipelineProgress status={document.status} /></td>
              </tr>
            ))}
            {!visible.length && <tr><td colSpan={5}><div className="empty-row"><Files size={20} /><strong>No documents found</strong><span>Upload a PDF or choose a different filter.</span></div></td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UploadArea({ uploads, onFiles, onClear }: { uploads: UploadItem[]; onFiles: (files: File[]) => void; onClear: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const accept = (files: File[]) => onFiles(files.filter((file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")));

  return (
    <section className="upload-section">
      <div className="section-title"><div><h2>Bulk upload</h2><p>Text-based PDFs, up to 50 MB each.</p></div>{uploads.length > 0 && <button className="text-button" onClick={onClear}>Clear finished</button>}</div>
      <button className={`drop-area ${dragging ? "is-dragging" : ""}`} onClick={() => input.current?.click()} onDragOver={(event) => event.preventDefault()} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); accept(Array.from(event.dataTransfer.files)); }}>
        <input ref={input} hidden multiple type="file" accept="application/pdf,.pdf" onChange={(event) => accept(Array.from(event.target.files || []))} />
        <Upload size={18} /><span><strong>Drop PDFs here</strong> or choose files</span><small>Multiple files are processed independently</small>
      </button>
      {uploads.length > 0 && <div className="upload-list">{uploads.map((item) => {
        const failed = item.status === "ERROR" || item.status === "FAILED";
        const done = item.status === "COMPLETED";
        return <div className="upload-item" key={item.key}><span className={`upload-state ${failed ? "failed" : done ? "done" : ""}`}>{failed ? <XCircle size={15} /> : done ? <Check size={15} /> : <FileText size={15} />}</span><div><div className="upload-item-head"><strong>{item.file.name}</strong><small>{fileSize(item.file.size)}</small></div><div className="upload-track"><span style={{ width: `${item.status === "uploading" ? item.progress : 100}%` }} /></div><p>{item.message || item.status.toLowerCase()}</p></div>{!failed && !done && <LoaderCircle className="spin" size={15} />}</div>;
      })}</div>}
    </section>
  );
}

function Overview({ documents, observability, health, refresh, refreshing, openView }: { documents: DocumentRecord[]; observability: Observability | null; health: Health | null; refresh: () => void; refreshing: boolean; openView: (view: View) => void }) {
  const ready = documents.filter((document) => document.status === "COMPLETED").length;
  const processing = documents.filter((document) => processingStates.includes(document.status)).length;
  const failed = documents.filter((document) => document.status === "FAILED").length;
  const total = Math.max(1, documents.length);
  return (
    <>
      <PageHeader eyebrow="Operations" title="Document operations" description="Current processing state for the demo tenant.">
        <button className="button button-secondary" onClick={refresh}><RefreshCw className={refreshing ? "spin" : ""} size={15} />Refresh</button>
        <button className="button button-primary" onClick={() => openView("documents")}><Upload size={15} />Upload documents</button>
      </PageHeader>
      {observability?.stuck_documents ? <button className="attention-banner" onClick={() => openView("documents")}><AlertCircle size={17} /><span><strong>{observability.stuck_documents} document{observability.stuck_documents === 1 ? "" : "s"} outside the processing window</strong><small>Open the document ledger to inspect recovery state.</small></span><ArrowRight size={16} /></button> : null}
      <div className="stat-strip">
        <div><span>Total documents</span><strong>{documents.length}</strong><small>Demo tenant</small></div>
        <div><span>Retrieval ready</span><strong>{ready}</strong><small>{Math.round((ready / total) * 100)}% of corpus</small></div>
        <div><span>Processing</span><strong>{processing}</strong><small>{observability?.queue_depth ?? 0} queued</small></div>
        <div><span>Failed</span><strong>{failed}</strong><small>Requires review</small></div>
      </div>
      <div className="overview-grid">
        <section className="surface recent-documents">
          <div className="surface-heading"><div><h2>Recent documents</h2><p>Latest activity across the ingestion pipeline.</p></div><button className="text-button" onClick={() => openView("documents")}>View all <ArrowRight size={13} /></button></div>
          <DocumentTable documents={documents} compact />
        </section>
        <aside className="surface system-panel">
          <div className="surface-heading"><div><h2>System status</h2><p>Live service and pipeline signals.</p></div><StatusTag status={health?.status || "connecting"} /></div>
          <div className="service-list">
            <div><span><Database size={15} />PostgreSQL</span><StatusTag status={health?.database === "up" ? "healthy" : "degraded"} /></div>
            <div><span><Server size={15} />RabbitMQ</span><StatusTag status={health?.rabbitmq === "up" ? "healthy" : "degraded"} /></div>
            <div><span><RotateCcw size={15} />Supervisor</span><strong>{observability?.supervisor_age_seconds == null ? "Unavailable" : `${observability.supervisor_age_seconds}s ago`}</strong></div>
            <div><span><HardDrive size={15} />Indexed chunks</span><strong>{observability?.chunk_count ?? "—"}</strong></div>
          </div>
          <div className="corpus-breakdown"><div className="breakdown-heading"><span>Corpus by state</span><strong>{documents.length}</strong></div><div className="breakdown-bar"><span className="ready" style={{ width: `${ready / total * 100}%` }} /><span className="working" style={{ width: `${processing / total * 100}%` }} /><span className="failed" style={{ width: `${failed / total * 100}%` }} /></div><div className="breakdown-legend"><span><i className="ready" />Ready</span><span><i className="working" />Processing</span><span><i className="failed" />Failed</span></div></div>
          <button className="system-link" onClick={() => openView("tests")}><FlaskConical size={15} /><span><strong>Run system checks</strong><small>4 read-only diagnostic scenarios</small></span><ChevronRight size={15} /></button>
        </aside>
      </div>
    </>
  );
}

function DocumentsView({ documents, uploads, onFiles, onClear, refresh, refreshing }: { documents: DocumentRecord[]; uploads: UploadItem[]; onFiles: (files: File[]) => void; onClear: () => void; refresh: () => void; refreshing: boolean }) {
  const [filter, setFilter] = useState<DocumentFilter>("all");
  return <><PageHeader eyebrow="Corpus" title="Documents" description="Upload, track, and inspect durable processing state."><button className="button button-secondary" onClick={refresh}><RefreshCw className={refreshing ? "spin" : ""} size={15} />Refresh</button></PageHeader><div className="documents-layout"><UploadArea uploads={uploads} onFiles={onFiles} onClear={onClear} /><section className="surface ledger"><div className="surface-heading"><div><h2>Document ledger</h2><p>{documents.length} records in the demo tenant.</p></div></div><DocumentTable documents={documents} filter={filter} onFilter={setFilter} /></section></div></>;
}

function SearchView({ documents, onComplete }: { documents: DocumentRecord[]; onComplete: () => void }) {
  const [query, setQuery] = useState("What are the access control requirements?");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const run = async () => { if (query.trim().length < 3) return; setLoading(true); setError(""); try { setResults(await api.searchDocuments(query)); onComplete(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Search failed"); } finally { setLoading(false); } };
  return <><PageHeader eyebrow="Retrieval" title="Semantic search" description="Rank source passages from completed documents. Results are evidence, not generated legal advice." /><div className="search-layout"><section className="search-form"><label htmlFor="query">Question</label><textarea id="query" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") run(); }} /><div className="query-examples"><span>Examples</span>{["Find termination notice periods", "What evidence is required for audits?", "Summarize liability limitations"].map((example) => <button onClick={() => setQuery(example)} key={example}>{example}</button>)}</div><button className="button button-primary search-button" onClick={run} disabled={loading}>{loading ? <LoaderCircle className="spin" size={15} /> : <Search size={15} />}Search corpus</button>{error && <p className="form-error"><AlertCircle size={14} />{error}</p>}</section><section className="search-results"><div className="results-heading"><div><h2>Ranked passages</h2><p>{results.length ? `${results.length} results` : "Run a query to inspect evidence"}</p></div>{results.length > 0 && <span>Highest similarity first</span>}</div>{results.length ? <div className="result-list">{results.map((result, index) => { const source = documents.find((document) => document.id === result.document_id); return <article className="search-result" key={`${result.document_id}-${index}`}><div className="result-index">{String(index + 1).padStart(2, "0")}</div><div><div className="result-source"><strong>{source?.name || result.document_id.slice(0, 8)}</strong><span>Page {result.page_number ?? "—"}</span><span className="score">{Math.round(result.score * 100)}% match</span></div><p>{result.content}</p></div></article>; })}</div> : <div className="search-empty"><FileSearch size={26} /><strong>No results to display</strong><p>Only completed documents in the demo tenant are searched.</p></div>}</section></div></>;
}

function TestsView() {
  const [running, setRunning] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ScenarioResult>>({});
  const run = async (id: string) => { setRunning(id); setExpanded(id); try { const result = await api.runScenario(id); setResults((current) => ({ ...current, [id]: result })); } catch (reason) { setResults((current) => ({ ...current, [id]: { scenario_id: id, outcome: "warning", summary: reason instanceof Error ? reason.message : "Test failed", evidence: [], executed_at: new Date().toISOString() } })); } finally { setRunning(null); } };
  return <><PageHeader eyebrow="Diagnostics" title="System tests" description="Read-only scenarios that inspect the running system and return concrete evidence." /><section className="surface test-suite"><div className="suite-header"><span>Test</span><span>Last result</span><span>Action</span></div>{scenarios.map((scenario) => { const result = results[scenario.id]; const isOpen = expanded === scenario.id; return <div className="test-row" key={scenario.id}><div className="test-main"><button className="expand-button" onClick={() => setExpanded(isOpen ? null : scenario.id)}><ChevronDown className={isOpen ? "open" : ""} size={15} /></button><span className="test-icon"><FlaskConical size={16} /></span><div><strong>{scenario.title}</strong><p>{scenario.description}</p></div></div><div>{result ? <><StatusTag status={result.outcome} /><small>{relativeTime(result.executed_at)}</small></> : <span className="not-run">Not run</span>}</div><button className="button button-secondary" disabled={running !== null} onClick={() => run(scenario.id)}>{running === scenario.id ? <LoaderCircle className="spin" size={14} /> : <Play size={14} />}{result ? "Run again" : "Run test"}</button>{isOpen && <div className="test-details"><p>{result?.summary || "Run this test to collect evidence from the live system."}</p>{result?.evidence.map((item) => <div className="evidence-row" key={item.label}><span>{item.healthy ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}{item.label}</span><strong>{item.value ?? "Unavailable"}{item.unit ? ` ${item.unit}` : ""}</strong></div>)}</div>}</div>; })}</section></>;
}

function ArchitectureView() {
  const [flowKey, setFlowKey] = useState<keyof typeof architectureFlows>("ingestion");
  const [selected, setSelected] = useState(0);
  const flow = architectureFlows[flowKey];
  return <><PageHeader eyebrow="System design" title="Architecture" description="Three paths explain how data moves, how tenant boundaries are applied, and how interrupted work recovers." /><div className="architecture-tabs">{(Object.keys(architectureFlows) as Array<keyof typeof architectureFlows>).map((key) => <button className={key === flowKey ? "active" : ""} onClick={() => { setFlowKey(key); setSelected(0); }} key={key}>{architectureFlows[key].label}</button>)}</div><section className="architecture-board"><div className="architecture-intro"><h2>{flow.label} path</h2><p>{flow.summary}</p></div><div className="architecture-flow">{flow.steps.map(([number, title], index) => <div className="architecture-step-wrap" key={title}><button className={`architecture-step ${selected === index ? "selected" : ""}`} onClick={() => setSelected(index)}><span>{number}</span><strong>{title}</strong></button>{index < flow.steps.length - 1 && <ArrowRight size={15} />}</div>)}</div><div className="architecture-detail"><span>{flow.steps[selected][0]}</span><div><h3>{flow.steps[selected][1]}</h3><p>{flow.steps[selected][2]}</p></div></div></section><section className="architecture-notes"><div><Shield size={17} /><span><strong>Tenant boundary</strong><small>Applied in the retrieval SQL, not after results are returned.</small></span></div><div><Database size={17} /><span><strong>Durable checkpoints</strong><small>State changes survive worker restarts and broker redelivery.</small></span></div><div><Activity size={17} /><span><strong>Observable by design</strong><small>Health, queue depth, latency, and recovery heartbeat are exposed.</small></span></div></section></>;
}

export default function App() {
  const [view, setView] = useState<View>("overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [observability, setObservability] = useState<Observability | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const [docs, obs, system] = await Promise.allSettled([api.getDocuments(), api.getObservability(), api.getHealth()]);
    if (docs.status === "fulfilled") setDocuments(docs.value);
    if (obs.status === "fulfilled") setObservability(obs.value);
    if (system.status === "fulfilled") setHealth(system.value);
    setRefreshing(false);
  }, []);

  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 5000); return () => window.clearInterval(timer); }, [refresh]);

  const updateUpload = (key: string, patch: Partial<UploadItem>) => setUploads((current) => current.map((item) => item.key === key ? { ...item, ...patch } : item));
  const poll = async (key: string, documentId: string) => { for (let attempt = 0; attempt < 120; attempt += 1) { await new Promise((resolve) => window.setTimeout(resolve, 2000)); try { const document = await api.getDocument(documentId); updateUpload(key, { status: document.status, message: document.is_stuck ? "Waiting for supervisor recovery" : `${document.chunk_count} chunks indexed` }); if (document.status === "COMPLETED" || document.status === "FAILED") { refresh(); return; } } catch { /* transaction may not be visible yet */ } } updateUpload(key, { status: "ERROR", message: "Progress polling timed out" }); };
  const handleFiles = (files: File[]) => { const incoming = files.map((file, index) => ({ key: `${Date.now()}-${index}-${file.name}`, file, progress: 0, status: "queued" as const })); setUploads((current) => [...incoming, ...current]); incoming.forEach(async (item) => { updateUpload(item.key, { status: "uploading", message: "Uploading" }); try { const documentId = await api.uploadDocument(item.file, (progress) => updateUpload(item.key, { progress })); updateUpload(item.key, { status: "UPLOADED", progress: 100, documentId, message: "Queued for processing" }); poll(item.key, documentId); refresh(); } catch (reason) { updateUpload(item.key, { status: "ERROR", message: reason instanceof Error ? reason.message : "Upload failed" }); } }); };
  const openView = (next: View) => { setView(next); setMobileNav(false); window.scrollTo({ top: 0, behavior: "smooth" }); };

  return (
    <div className="app">
      <header className="global-header"><button className="mobile-nav-button" onClick={() => setMobileNav(true)}><Menu size={18} /></button><div className="wordmark"><span><Shield size={16} /></span><strong>LexGuard</strong></div><div className="environment"><span className={health?.status === "healthy" ? "healthy" : "degraded"} /><strong>Demo environment</strong><small>Tenant: demo</small></div><div className="header-meta"><span>Auto-refresh 5s</span><button onClick={refresh} aria-label="Refresh"><RefreshCw className={refreshing ? "spin" : ""} size={15} /></button></div></header>
      <div className="app-body">
        <nav className={`sidebar ${mobileNav ? "is-open" : ""}`}><div className="nav-label">Workspace</div>{navItems.map((item) => { const Icon = item.icon; return <button className={view === item.id ? "active" : ""} onClick={() => openView(item.id)} key={item.id}><Icon size={16} /><span>{item.label}</span>{item.id === "documents" && observability?.stuck_documents ? <b>{observability.stuck_documents}</b> : null}</button>; })}<div className="sidebar-system"><span>System</span><div><i className={health?.database === "up" ? "healthy" : "degraded"} />Database</div><div><i className={health?.rabbitmq === "up" ? "healthy" : "degraded"} />Message queue</div></div></nav>
        {mobileNav && <button className="nav-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18} /></button>}
        <main className="main-content">
          {view === "overview" && <Overview documents={documents} observability={observability} health={health} refresh={refresh} refreshing={refreshing} openView={openView} />}
          {view === "documents" && <DocumentsView documents={documents} uploads={uploads} onFiles={handleFiles} onClear={() => setUploads((current) => current.filter((item) => !["COMPLETED", "FAILED", "ERROR"].includes(item.status)))} refresh={refresh} refreshing={refreshing} />}
          {view === "search" && <SearchView documents={documents} onComplete={refresh} />}
          {view === "tests" && <TestsView />}
          {view === "architecture" && <ArchitectureView />}
        </main>
      </div>
    </div>
  );
}
