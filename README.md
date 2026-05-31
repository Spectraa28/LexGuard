# LexGuard

A Legal Inference and AI Observability Control Plane. LexGuard ingests legal documents, chunks and embeds them into a pgvector store, and exposes a guardrailed RAG inference layer for legal question answering with full audit traceability.

---

## Architecture Overview

```
HTTP Upload (Spring Boot)
    └── Cloudflare R2 (raw PDF storage)
    └── PostgreSQL (document metadata + outbox)
    └── RabbitMQ (async event bus)
            └── Python Embedding Worker
                    └── Unstructured.io (PDF parsing)
                    └── SentenceTransformers (vector generation)
                    └── pgvector (HNSW similarity index)
```

---

## Local Development Setup

### Prerequisites

- Docker and Docker Compose
- Java 21
- Maven
- Python 3.10+
- Miniconda or virtualenv

### Step 1 — Boot the infrastructure

The `ingestion-service` Docker Compose file starts PostgreSQL (with the pgvector extension), RabbitMQ, and their management UIs in a single command.

```bash
cd ingestion-service
docker compose up -d
```

PostgreSQL will be available at `localhost:5432` and RabbitMQ management UI at `localhost:15672` (guest/guest).

### Step 2 — Start the Spring Boot ingestion service

Flyway will automatically apply all migrations (V1 through V5) on startup, creating the full schema including the pgvector HNSW index and the `document_status` enum.

```bash
cd ingestion-service
./mvnw spring-boot:run
```

The ingestion API will be available at `http://localhost:8080`.

### Step 3 — Start the Python embedding worker

The worker connects to the same PostgreSQL instance and RabbitMQ broker defined in the Docker Compose. Install dependencies and run with unbuffered output so the full traceback is visible on any exception.

```bash
cd embedding-worker
pip install -r requirements.txt
python -u worker.py
```

### Environment Configuration

Copy `ingestion-service/src/main/resources/application-example.yml` to `application.yml` and fill in the required values. The embedding worker reads its configuration from environment variables defined in `embedding-worker/config.py`. An example `.env` structure for the worker:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/lexguard
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET_NAME=your_bucket_name
```

### Uploading a document

Once all three services are running, upload a PDF through the ingestion API:

```bash
curl -X POST http://localhost:8080/api/v1/documents/upload \
  -F "file=@your_contract.pdf" \
  -F "tenantId=tenant-001" \
  -F "fileName=your_contract.pdf"
```

The worker will log the full pipeline progression and the document will reach `COMPLETED` status in the database.

### Verifying a successful run

```sql
SELECT id, status, version, updated_at
FROM documents
ORDER BY created_at DESC
LIMIT 5;
```

A healthy single-pass run completes at `version = 5`, reflecting five atomic state transitions across the Spring Boot parsing phase and the Python embedding phase.

---

## Phase 1 — Async Ingestion (Sessions 1–3)

### Transactional Outbox Pattern (Session 1)

The Spring Boot service never publishes directly to RabbitMQ. Every document upload writes to the `documents` table and the `outbox_messages` table inside a single database transaction. A scheduled relay process reads unpublished outbox rows and publishes them to RabbitMQ, marking each row `PUBLISHED` only after the broker confirms receipt. This guarantees that no message is lost even if the broker is temporarily unavailable at upload time.

The upload endpoint returns `202 Accepted` immediately, confirming the document is durably stored before any asynchronous processing begins.

### Schema and Migrations (Session 2)

Flyway-managed schema with five verified migrations. Core tables:

`documents` — tenant-isolated metadata with a six-state PostgreSQL enum (`UPLOADED → PARSED → EMBEDDING → EMBEDDED → COMPLETED → FAILED`), an `is_latest` flag for contract version routing, and a `version` integer column for optimistic locking.

`document_lineage` — append-only parent/child adjacency list with a unique constraint on `parent_document_id` enforcing single-child amendment chains.

`document_chunks` — layout-aware text fragments with page number and chunk type metadata for legal citation traceability.

`chunk_embeddings` — separated vector table with a `(chunk_id, model_name)` unique constraint enabling zero-downtime embedding model upgrades. HNSW index tuned at `m=16, ef_construction=128` for high-recall legal retrieval.

### Python Embedding Worker (Session 2)

State-driven checkpoint pipeline consuming from RabbitMQ:

`models.py` — SQLAlchemy 2.0 declarative ORM with pgvector integration and `version_id_col` wired to the `documents.version` column for automatic optimistic locking.

`processor.py` — resumable pipeline with two independently checkpointed phases (parse, embed), distinguishing transient failures (R2 network errors, database deadlocks — NACK with requeue) from terminal failures (corrupted PDF, invalid model — mark FAILED, ACK to drain the message).

`worker.py` — pika consumer with `prefetch_count=1`, `heartbeat=600`, and explicit ACK/NACK routing mapping processor signals to RabbitMQ protocol.

### State Machine Hardening and Optimistic Locking (Session 3)

Added `EMBEDDING` as an explicit distributed lock state written durably to PostgreSQL before the `SentenceTransformer` computation begins. This allows a future supervisor sweep to distinguish an actively processing worker from a crashed one by checking both the status column and the `updated_at` timestamp together.

Added a `version` integer column (Flyway V5) to the `documents` table, defaulting to 1. The `version_id_col` mapper in SQLAlchemy automatically appends a version predicate to every update. If a supervisor sweep re-queues a document while the original worker is still computing, the slow worker's final commit raises `StaleDataError`, which is caught and handled as `SKIP_SUPERSEDED` — the worker rolls back all pending chunk embeddings and ACKs the message without crashing or polluting the vector store.

### RAG Retrieval Layer (Session 3)

`retrieval.py` exposes a `retrieve_relevant_chunks` function that performs cosine similarity search against the embedded vector store. The query uses a CTE to cast the query vector exactly once, joins across `chunk_embeddings`, `document_chunks`, and `documents`, and enforces two mandatory business filters: `documents.status = 'COMPLETED'` to exclude in-progress documents and `documents.is_latest = true` to exclude superseded contract versions. A configurable distance threshold (default `0.5`) prevents semantically irrelevant chunks from reaching the generation layer. Results are returned as typed `SearchResult` dataclasses containing `content`, `page_number`, and `distance`.

The retrieval function is verified against a live ingested document and correctly returns zero results for queries outside the document's semantic domain, confirming the threshold filter is functioning as a noise gate rather than a bug.

---

## Phase 2 — Guardrailed Inference (Upcoming)

Phase 2 will introduce the inference control plane in front of the retrieval layer: Llama Guard for input and output screening, a SemanticCache backed by Faiss and Redis for repeat-query deduplication, a DeepSeek generation model, and an append-only audit log for full observability of every inference decision. The `/query` FastAPI endpoint will be wired in this phase.

---

## Repository Structure

```
LexGuard/
├── ingestion-service/          # Spring Boot 3.5 / Java 21 async ingestion API
│   ├── src/main/java/          # Controllers, services, outbox relay, R2 storage
│   └── src/main/resources/
│       ├── application.yml
│       ├── application-example.yml
│       └── db/migration/       # V1–V5 Flyway migrations
└── embedding-worker/           # Python 3.10 async embedding pipeline
    ├── worker.py               # pika RabbitMQ consumer
    ├── processor.py            # State-driven parse + embed pipeline
    ├── models.py               # SQLAlchemy 2.0 ORM with pgvector
    ├── retrieval.py            # pgvector cosine similarity search
    ├── config.py               # Environment-based configuration
    └── requirements.txt
```