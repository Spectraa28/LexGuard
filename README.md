# LexGuard

**Tenant-safe semantic retrieval for private legal documents, backed by an observable and recoverable ingestion pipeline.**

LexGuard accepts PDF documents, processes them asynchronously, and returns ranked, page-level evidence through semantic search. The project focuses on the infrastructure concerns that are often skipped in RAG demos: durable events, tenant isolation, idempotent processing, stuck-job recovery, correlation IDs, metrics, and operational visibility.

![LexGuard architecture](architecture/Flow.png)

## What it demonstrates

- **Asynchronous PDF ingestion** through Spring Boot, PostgreSQL, RabbitMQ, and a Python worker.
- **Transactional outbox delivery** so document state and its processing event are committed together.
- **Tenant-scoped retrieval** enforced inside the vector-search SQL query.
- **Evidence-first results** with document, page, content, and similarity lineage.
- **Recoverable processing** using durable checkpoints, optimistic locking, and a supervisor for abandoned jobs.
- **Operational visibility** through Prometheus, Grafana, health checks, queue depth, and correlation-aware logs.
- **Interactive control plane** for bulk upload, progress, stuck documents, search, system checks, and architecture walkthroughs.

## System overview

### Ingestion path

```text
PDF upload
  → Spring Boot ingestion API
  → Cloudflare R2 + PostgreSQL document/outbox transaction
  → RabbitMQ
  → Python parsing and embedding worker
  → PostgreSQL + pgvector HNSW index
```

### Retrieval path

```text
Search request
  → FastAPI authentication and validation
  → query embedding
  → tenant-bound pgvector cosine search
  → ranked page-level passages
```

### Recovery path

```text
Supervisor heartbeat
  → detect stale intermediate states
  → lock rows with FOR UPDATE SKIP LOCKED
  → restore the last safe checkpoint
  → publish a new outbox event
  → resume processing
```

![Docker topology](architecture/Docker.png)

## Technology

| Area | Technology |
|---|---|
| Control plane | React 18, TypeScript, Vite, Nginx |
| Ingestion API | Java 21, Spring Boot 3.5, Flyway |
| Retrieval API | Python 3.12, FastAPI, SQLAlchemy 2 |
| Processing | pypdf, SentenceTransformers, PyTorch CPU |
| Embeddings | `all-MiniLM-L6-v2`, 384 dimensions |
| Persistence | PostgreSQL 16, pgvector, HNSW |
| Messaging | RabbitMQ 3 with publisher confirms |
| Object storage | Cloudflare R2 |
| Observability | Prometheus, Grafana, structured correlation IDs |
| Runtime | Docker Compose |

## Run locally

### Requirements

- Docker with Docker Compose
- A Cloudflare R2 bucket and API credentials
- A text-based PDF for testing

Scanned or image-only PDFs require OCR, which is intentionally not included in the lightweight worker image.

### 1. Configure the environment

Create a root `.env` file. It is ignored by Git.

```env
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY=your_r2_access_key
R2_SECRET_KEY=your_r2_secret_key
R2_BUCKET_NAME=your_bucket_name
DEMO_TENANT_ID=demo
```

### 2. Start the stack

Use the launcher to build the images, start the services, and wait for the API and UI:

```bash
./scripts/demo.sh start
```

Or run Compose directly:

```bash
docker compose up --build --detach
```

The first worker start can take longer while the embedding model is populated in the persistent `model_cache` volume.

### 3. Open the services

| Service | URL | Credentials |
|---|---|---|
| LexGuard UI | `http://localhost:8088` | — |
| FastAPI docs | `http://localhost:8000/docs` | — |
| RabbitMQ management | `http://localhost:15672` | `guest` / `guest` |
| Grafana | `http://localhost:3000` | `admin` / `admin` |
| Prometheus | `http://localhost:9090` | — |

The UI provides the quickest demo path: upload PDFs, follow their durable state, search completed documents, run system scenarios, and inspect the architecture.

### 4. Manage the stack

```bash
./scripts/demo.sh status  # container status and service URLs
./scripts/demo.sh logs    # follow application-service logs
./scripts/demo.sh stop    # stop containers without deleting volumes
```

## API examples

### Upload a PDF

The UI uses the `demo` tenant. Use the same tenant from the command line if you want the document to appear there.

```bash
curl -X POST http://localhost:8080/api/v1/documents \
  -H "X-Tenant-ID: demo" \
  -F "file=@contract.pdf;type=application/pdf"
```

The ingestion API returns `202 Accepted` after the file and durable processing request have been recorded.

### Search the demo corpus

```bash
curl -X POST http://localhost:8000/demo/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What notice is required before termination?","limit":5}'
```

### Inspect health and metrics

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

### Verify document state

```bash
docker exec lexguard-postgres psql -U admin -d lexguard \
  -c "SELECT id, tenant_id, status, version, updated_at FROM documents ORDER BY created_at DESC LIMIT 10;"
```

## API reference

| Endpoint | Authentication | Purpose |
|---|---|---|
| `POST :8080/api/v1/documents` | `X-Tenant-ID` | Upload a PDF for asynchronous processing |
| `POST :8000/query` | `X-API-Key` | Authenticated, tenant-scoped semantic retrieval |
| `POST :8000/demo/query` | Demo rate limit | Search the configured demo tenant |
| `GET :8000/demo/documents` | Demo environment | List documents and processing state |
| `GET :8000/demo/documents/{id}` | Demo environment | Poll a document's current state |
| `GET :8000/demo/observability` | Demo environment | Read queue, corpus, vector, and supervisor signals |
| `POST :8000/demo/scenarios/{id}` | Demo environment | Run a pipeline, recovery, isolation, or retrieval check |
| `GET :8000/health` | None | Database, broker, queue, and recovery health |
| `GET :8000/metrics` | None | Prometheus metrics |

The public demo query is limited to 10 requests per minute per IP. Authenticated retrieval is limited per tenant.

## Engineering decisions

### Transactional outbox

The ingestion service does not publish directly to RabbitMQ inside the upload request. It commits the document and an outbox row in one PostgreSQL transaction. A scheduled relay claims unpublished rows with `FOR UPDATE SKIP LOCKED`, publishes with broker confirms, and marks successful deliveries as published.

This provides durable, at-least-once delivery. Duplicate execution is handled by state checks, optimistic locking, and uniqueness constraints rather than by claiming exactly-once messaging.

### Tenant isolation

Authenticated retrieval resolves an API key to a tenant and binds that tenant directly into the pgvector query. The query also restricts results to completed, current document versions. Cross-tenant rows never enter the candidate result set.

### Processing checkpoints

Documents advance through durable states:

```text
UPLOADED → PARSED → EMBEDDED → EMBEDDING → COMPLETED
```

The worker uses `prefetch_count=1`, records the embedding lock state before inference, and distinguishes retryable infrastructure errors from terminal document failures. Optimistic versioning prevents two consumers from committing the same transition.

### Recovery supervisor

The supervisor periodically searches for stale intermediate states. Each document is recovered in its own database session, using row locking and a staged rollback map. A failure while recovering one document does not roll back the rest of the sweep.

### Correlation and metrics

- The Java relay sends the document ID as the AMQP `correlation_id`.
- The worker reads correlation metadata before decoding the message body.
- FastAPI propagates `X-Correlation-ID` through retrieval logs using `contextvars`.
- Prometheus exposes vector-search latency, queue depth, stuck-document count, and supervisor heartbeat freshness.

## Tests

Run the lightweight Python tests without loading the full embedding model:

```bash
cd embedding-worker
python -m unittest test_pdf_parser.py test_retrieval.py test_tenant_retrieval.py
```

Build the production frontend:

```bash
npm --prefix frontend install
npm --prefix frontend run build
```

Validate the Compose file:

```bash
docker compose config --quiet
```

## Repository layout

```text
LexGuard/
├── frontend/                  React control plane and Nginx reverse proxy
├── ingestion-service/         Spring Boot upload API and Flyway migrations
├── embedding-worker/          FastAPI, worker, retrieval, and supervisor
├── architecture/              System and container diagrams
├── scripts/demo.sh            Local stack launcher
├── docker-compose.yml         Nine-service development topology
└── prometheus.yml             Metrics scrape configuration
```

## Troubleshooting

### `port is already allocated`

Another process or container is already using one of LexGuard's host ports. For example, inspect API port `8000` and stop the conflicting container or process:

```bash
docker ps --filter publish=8000
docker compose down
```

If port `8000` must remain occupied, change the API mapping in `docker-compose.yml` from `8000:8000` to `8001:8000`. The frontend communicates with the API over the Compose network, so its internal address remains unchanged.

### UI shows degraded services

```bash
./scripts/demo.sh status
./scripts/demo.sh logs
```

The API depends on healthy PostgreSQL and RabbitMQ. The ingestion service additionally requires valid R2 credentials.

### Upload completes but processing does not

Confirm that the worker is running, RabbitMQ is reachable, and the document is a text-based PDF. Then inspect the worker and supervisor logs.

## Scope

LexGuard is an engineering demonstration, not a legal-advice system. It returns relevant source passages and operational evidence; it does not replace legal review. Production deployment would additionally require managed secrets, TLS, hardened identity and authorization, storage lifecycle policies, backups, alerting, and an OCR path for scanned documents.

---

Built by [Sonu Verma](https://github.com/Spectraa28).
