# LexGuard

A Legal Inference and AI Observability Control Plane. LexGuard ingests legal documents, chunks and embeds them into a pgvector store, and exposes a guardrailed RAG inference layer for legal question answering with full audit traceability.

---

## Architecture Overview

```
HTTP Upload (Spring Boot :8080)
    └── Cloudflare R2 (raw PDF storage)
    └── PostgreSQL (document metadata + outbox)
    └── RabbitMQ (async event bus)
            └── Python Embedding Worker
                    └── Unstructured.io (PDF parsing)
                    └── SentenceTransformers all-MiniLM-L6-v2 (vector generation)
                    └── pgvector HNSW index (similarity search)
            └── Python Supervisor (ghost document recovery)
            └── FastAPI RAG API (:8000)
```

---

## Verified Pipeline

Upload a legal PDF → Spring Boot stores to R2 and writes a transactional outbox event → RabbitMQ relay delivers the message → Python worker parses, chunks, and embeds the document → pgvector stores 384-dimensional vectors under HNSW → FastAPI `/query` endpoint returns semantically ranked chunks.

A healthy single-pass run completes at `version = 5`, reflecting five atomic state transitions. The supervisor sweep detects documents stuck in any non-terminal state beyond the timeout threshold and rolls them back to the last safe checkpoint automatically.

Tested end-to-end on ISO 27001:2022. RAG query returning real chunks at cosine similarity score `0.6233`. Supervisor rollback verified: `EMBEDDING → PARSED` at `version = 6`.

---

## Quick Start (Docker Compose)

### Prerequisites

- Docker and Docker Compose
- Cloudflare R2 bucket with API credentials

### Step 1 — Configure environment

Create a `.env` file at the project root:

```env
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY=your_r2_access_key
R2_SECRET_KEY=your_r2_secret_key
R2_BUCKET_NAME=your_bucket_name
```

### Step 2 — Build and start all services

```bash
docker compose build
docker compose up
```

This starts six services: `postgres`, `rabbitmq`, `ingestion-service`, `embedding-worker`, `supervisor`, and `api`. Flyway migrations run automatically on ingestion service startup, applying V1 through V6.

Wait for:
- `lexguard-ingestion` — `Started LexGuardIngestionApplication`
- `lexguard-api` — `Uvicorn running on http://0.0.0.0:8000`
- `lexguard-worker` — `Embedding Worker successfully started`

### Step 3 — Upload a document

```bash
curl -X POST http://localhost:8080/api/v1/documents \
  -H "X-Tenant-ID: tenant-001" \
  -F "file=@your_contract.pdf;type=application/pdf"
```

Response:
```json
{
  "documentId": "...",
  "status": "UPLOADED",
  "message": "Document successfully stored and queued for ML processing."
}
```

### Step 4 — Query the document

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the access control requirements", "limit": 3}'
```

### Step 5 — Verify pipeline state

```bash
docker exec lexguard-postgres psql -U admin -d lexguard \
  -c "SELECT id, status, version, updated_at FROM documents ORDER BY created_at DESC LIMIT 5;"
```

A completed document shows `status = COMPLETED` and `version = 5`.

---

## Local Development (Alternative)

### Prerequisites

- Java 21, Maven
- Python 3.10+
- PostgreSQL 16 with pgvector extension
- RabbitMQ

### Spring Boot ingestion service

```bash
cd ingestion-service
./mvnw spring-boot:run
```

Copy `src/main/resources/application-example.yml` to `application.yml` and fill in your database, RabbitMQ, and R2 credentials. Flyway applies all migrations automatically on startup.

### Python worker and API

```bash
cd embedding-worker
pip install -r requirements.txt
python -u worker.py        # embedding worker
python supervisor.py       # supervisor sweep
uvicorn main:app --port 8000  # RAG API
```

Configure via environment variables matching `config.py`. The worker reads `DATABASE_URL`, `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USER`, `RABBITMQ_PASS`, `RABBITMQ_QUEUE`, and the R2 credentials.

---

## Phase 1 — Async Ingestion Pipeline (Sessions 1–4)

### Transactional Outbox Pattern (Session 1)

The Spring Boot service never publishes directly to RabbitMQ. Every document upload atomically writes to both the `documents` table and the `outbox_messages` table inside a single database transaction. A scheduled relay process polls unpublished outbox rows using `FOR UPDATE SKIP LOCKED` and publishes them to RabbitMQ, marking each row `PUBLISHED` only after the broker confirms receipt via synchronous publisher confirms.

This guarantees no message is lost even if the broker is temporarily unavailable at upload time. The upload endpoint returns `202 Accepted` immediately, confirming the document is durably stored before any asynchronous processing begins.

### Schema and Migrations (Session 2)

Flyway-managed schema with six verified migrations (V1–V6). Core tables:

`documents` — tenant-isolated metadata with a six-state PostgreSQL enum (`UPLOADED → PARSED → EMBEDDED → EMBEDDING → COMPLETED → FAILED`), an `is_latest` flag for contract version routing, and a `version` integer column for optimistic locking.

`document_lineage` — append-only parent/child adjacency list with a unique constraint on `parent_document_id` enforcing single-child amendment chains.

`document_chunks` — layout-aware text fragments with page number and chunk type metadata for legal citation traceability.

`chunk_embeddings` — separated vector table with a `(chunk_id, model_name)` unique constraint enabling zero-downtime embedding model upgrades. HNSW index tuned at `m=16, ef_construction=128` for high-recall legal retrieval.

`outbox_events` — Python-side outbox table with `server_default` enforced at the DDL layer, ensuring the `PENDING` initial state is guaranteed even for out-of-band inserts from the Java relay.

### Python Embedding Worker (Session 2)

State-driven checkpoint pipeline consuming from RabbitMQ with `prefetch_count=1` and `heartbeat=600` to survive heavy CPU-bound embedding runs:

`models.py` — SQLAlchemy 2.0 declarative ORM with pgvector integration and `version_id_col` wired to the `documents.version` column for automatic optimistic locking.

`processor.py` — resumable pipeline with two independently checkpointed phases (parse, embed), distinguishing transient failures (R2 network errors, database deadlocks — NACK with requeue) from terminal failures (corrupted PDF, invalid model — mark FAILED, ACK to drain the message).

`worker.py` — pika consumer with explicit ACK/NACK routing mapping processor signals to RabbitMQ protocol.

### State Machine Hardening and Optimistic Locking (Session 3)

`EMBEDDING` is an explicit distributed lock state written durably to PostgreSQL before the `SentenceTransformer` computation begins. This allows the supervisor sweep to distinguish an actively processing worker from a crashed one by checking both the status column and the `updated_at` timestamp together.

The `version` integer column (Flyway V5) enables optimistic locking via SQLAlchemy's `version_id_col`. If a supervisor sweep re-queues a document while the original worker is still computing, the slow worker's final commit raises `StaleDataError`, which is caught and handled as `SKIP_SUPERSEDED` — the worker rolls back all pending chunk embeddings and ACKs the message without crashing or polluting the vector store.

### RAG Retrieval and Supervisor Sweep (Session 4)

`retrieval.py` exposes a `query_documents` orchestrator that embeds the raw query text using `all-MiniLM-L6-v2`, executes a CTE-optimised cosine similarity search via pgvector, and returns typed `SearchResult` dataclasses. The query enforces two mandatory business filters: `documents.status = 'COMPLETED'` to exclude in-progress documents and `documents.is_latest = true` to exclude superseded contract versions. A configurable distance threshold (default `0.5`) acts as a noise gate. Cosine distance is converted to similarity score via `1.0 - distance` before returning to the client.

`supervisor.py` runs as a standalone background process on a configurable sweep interval. It detects documents stuck in any non-terminal state beyond the timeout threshold and applies a staged rollback map: `EMBEDDING → PARSED` (wipes potentially corrupted chunk data via cascade delete), `PARSED → UPLOADED` (forces full re-parse), `EMBEDDED` and `UPLOADED` remain unchanged (durable checkpoints requiring only a fresh outbox event). Each document is processed in a fully isolated SQLAlchemy session with `FOR UPDATE SKIP LOCKED` to prevent multiple supervisor instances from double-processing the same document. The sweep interval is configured at a strict fraction of the timeout threshold to avoid the temporal aliasing race where a healthy worker's document is swept mid-flight.

`main.py` exposes a FastAPI `/query` endpoint with Pydantic request validation, dataclass-to-dict conversion, and two-layer exception handling distinguishing database connection failures from general pipeline errors.

---

## Repository Structure

```
LexGuard/
├── docker-compose.yml              # Unified 6-service compose (project root)
├── .env                            # R2 credentials (not committed)
├── ingestion-service/              # Spring Boot 3.5 / Java 21 async ingestion API
│   ├── Dockerfile
│   ├── src/main/java/              # Controllers, services, outbox relay, R2 storage
│   └── src/main/resources/
│       ├── application.yml
│       ├── application-example.yml
│       └── db/migration/           # V1–V6 Flyway migrations
└── embedding-worker/               # Python 3.12 async embedding pipeline
    ├── Dockerfile
    ├── worker.py                   # pika RabbitMQ consumer
    ├── processor.py                # State-driven parse + embed pipeline
    ├── supervisor.py               # Ghost document recovery sweep
    ├── models.py                   # SQLAlchemy 2.0 ORM with pgvector + OutboxEvent
    ├── retrieval.py                # pgvector cosine similarity search + orchestrator
    ├── main.py                     # FastAPI /query endpoint
    ├── config.py                   # Environment-based configuration
    └── requirements.txt
```

---

## Phase 2 — Active Observability Layer (Upcoming)

Phase 2 will instrument every pipeline boundary with correlation IDs, expose a Prometheus `/metrics` endpoint with query latency histograms and supervisor recovery counters, and add an active `/health` endpoint returning real-time pipeline state including stuck document counts, last sweep time, and queue depth.