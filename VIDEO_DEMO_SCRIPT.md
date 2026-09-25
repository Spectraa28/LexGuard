# LexGuard — three-minute video demo

## Preparation

- Start with `./scripts/demo.sh start` and record `http://localhost:8088`.
- Have one text-based PDF fully indexed and a second PDF ready for live upload.
- Warm semantic search once before recording.

## 0:00–0:20 — Introduction

**Screen:** Overview.

> This is LexGuard, a tenant-isolated document intelligence platform for legal PDFs. It combines asynchronous processing, semantic retrieval, automated recovery, and live operational visibility. Everything in this interface comes from the running system rather than hard-coded demo data.

Point to retrieval-ready documents, processing count, service health, and indexed chunks.

## 0:20–0:55 — Upload and processing

**Screen:** Documents. Upload the second PDF.

> Users can upload multiple PDFs and monitor each independently. The ingestion API stores the file and atomically commits its metadata with a transactional outbox event. RabbitMQ delivers that event to the embedding worker, which extracts text, creates page-aware chunks and vectors, and stores them in PostgreSQL with pgvector.

> The interface follows durable states from uploaded through parsing, embedding, and completion. Refreshing the browser does not lose or fabricate progress. Work outside the processing window is marked as stuck and becomes eligible for supervised recovery.

## 0:55–1:30 — Tenant-safe retrieval

**Screen:** Search. Ask: “What notice is required before termination?”

> Once processing completes, the document becomes searchable. Tenant isolation is enforced inside the database query before vector ranking—not afterward in application code.

Point to the document name, page, score, and passage.

> Every result retains document and page lineage. LexGuard returns verifiable evidence instead of presenting unsupported generated legal advice.

## 1:30–2:05 — System verification

**Screen:** System tests. Run **Tenant isolation**, then **Recovery supervisor**.

> These read-only scenarios inspect the running services. Tenant isolation reports which records are visible and excluded. Recovery verifies the supervisor heartbeat and detects documents exceeding the processing timeout.

Expand the returned evidence.

> The checks return concrete system evidence. An unavailable dependency produces a warning instead of a fake success animation.

## 2:05–2:45 — Architecture

**Screen:** Architecture. Click through Ingestion, Retrieval, and Recovery.

> The write path begins in Spring Boot. Document state and the outbox event commit atomically, RabbitMQ decouples the request from expensive processing, and the Python worker extracts, chunks, embeds, and stores vectors in pgvector.

> On the read path, FastAPI binds the tenant directly into SQL before cosine ranking. For resilience, the supervisor locks abandoned work with skip-locked semantics, restores its last safe checkpoint, and requeues it without duplicating vectors.

## 2:45–3:00 — Close

**Screen:** Overview.

> LexGuard is more than a PDF search interface. It demonstrates durable event-driven processing, database-level tenant isolation, evidence-based retrieval, self-healing recovery, and observability across Java and Python services—all packaged as a reproducible Docker Compose application.

**End card:** LexGuard — tenant-safe document intelligence with observable, recoverable infrastructure.

Do not wait for live embedding on camera. Demonstrate progress with the new upload, then search the document indexed before recording.
