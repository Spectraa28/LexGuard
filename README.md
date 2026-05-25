# LexGuard — Ingestion Service (Phase 1)

> Asynchronous document ingestion pipeline for the LexGuard Legal Inference and AI Observability Control Plane.

## What This Service Does

Legal and compliance teams upload PDF contracts through the Next.js frontend. This Spring Boot service accepts those uploads and guarantees they reach the downstream Python ML workers without data loss — even under peak morning load spikes or infrastructure failures.

The core architectural guarantee: **a single ACID transaction writes both the document record and the outbox event**. If the application crashes between the database write and the RabbitMQ publish, the Transactional Outbox Pattern ensures the message is never lost.

---

## Architecture

```
Next.js Frontend
      │
      │  POST /api/v1/documents (multipart/form-data)
      ▼
Spring Boot Ingestion Service
      │
      ├─ 1. Stream PDF → Cloudflare R2            (non-transactional, no DB connection held)
      │
      ├─ 2. ACID dual-write (single transaction)
      │       ├─ INSERT documents (status: UPLOADED)
      │       └─ INSERT outbox_messages (status: PENDING)
      │
      └─ 3. Background OutboxMessageRelay (@Scheduled)
              ├─ SELECT ... FOR UPDATE SKIP LOCKED  (multi-pod safe)
              ├─ Publish to RabbitMQ with publisher confirms
              └─ UPDATE outbox_messages (status: PUBLISHED | FAILED)
                        │
                        ▼
              RabbitMQ: lexguard.document.parsing.queue
                        │
                        ▼
              Phase 2: Python ML Workers (OCR → Chunking → PgVector)
```

### Key Design Decisions

**Transaction boundary after S3 upload.** Holding a database connection open during a network stream exhausts the Hikari pool under concurrent load. The PostgreSQL connection only opens after R2 confirms the upload.

**Transactional Outbox Pattern.** Eliminates the dual-write problem between object storage and the message broker. The outbox event shares the same database transaction as the document record — both commit or neither does.

**`FOR UPDATE SKIP LOCKED`.** The relay uses a native PostgreSQL query with row-level locking. If two pods sweep the outbox simultaneously, they receive different batches without lock collisions or duplicate RabbitMQ publishes.

**Synchronous publisher confirms.** The relay blocks up to 5 seconds for a broker ACK before marking a message as a transient failure. After 5 retries the message is marked `FAILED` to prevent a corrupted payload from blocking healthy uploads indefinitely.

---

## Tech Stack

| Component | Technology |
|---|---|
| Web Framework | Spring Boot 3.5.0 (Java 21) |
| Message Broker | RabbitMQ 3 (AMQP) |
| Database | PostgreSQL 15 + JPA/Hibernate |
| Object Storage | Cloudflare R2 (AWS SDK v2) |
| Scheduler | Spring `@Scheduled` + `@EnableScheduling` |
| Serialization | Jackson with `JavaTimeModule` (ISO-8601 timestamps) |

---

## Project Structure

```
ingestion-service/
└── src/main/java/com/lexguard/ingestion/
    ├── LexGuardIngestionApplication.java
    ├── config/
    │   ├── MessagingConfig.java          # RabbitMQ topology (exchange, queue, binding, converter)
    │   └── StorageConfig.java            # Cloudflare R2 S3 client bean
    ├── controller/
    │   ├── DocumentIngestionController.java
    │   └── advice/GlobalExceptionHandler.java
    ├── model/
    │   ├── Document.java                 # Primary domain entity (UPLOADED → PROCESSING → COMPLETED)
    │   ├── DocumentUploadRequest.java    # Ephemeral input DTO with Jakarta validation
    │   ├── IngestionTaskEvent.java       # Immutable domain event (Java record)
    │   └── OutboxMessage.java            # Transactional outbox entity with state machine
    ├── repository/
    │   ├── DocumentRepository.java
    │   └── OutboxMessageRepository.java  # Native SKIP LOCKED query
    └── service/
        ├── IngestionOrchestrator.java    # Coordinates S3 upload and persistence boundary
        ├── RabbitEventPublisher.java     # Raw AMQP publish with synchronous confirms
        ├── S3StorageProvider.java        # Streams multipart file to R2, returns StorageResult
        ├── TransactionalOutboxService.java  # Propagation.MANDATORY — chains to parent transaction
        ├── OutboxMessageRelay.java       # @Scheduled sweeper with retry logic
        └── persistence/
            └── DocumentPersistenceService.java  # @Transactional boundary, crosses AOP proxy
```

---

## Local Setup

### Prerequisites

- Java 21
- Maven 3.9+
- Docker Desktop

### 1. Start Infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (port 5432) and RabbitMQ (port 5672, management UI on 15672).

### 2. Configure the Application

Create `ingestion-service/src/main/resources/application-local.yml` — this file is gitignored and must never be committed:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/lexguard
    username: your_db_user
    password: your_db_password
  jpa:
    hibernate:
      ddl-auto: update   # use 'validate' + Flyway in production
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    publisher-confirm-type: correlated

cloudflare:
  r2:
    account-id: your_account_id
    access-key: your_r2_access_key
    secret-key: your_r2_secret_key
    bucket-name: your_bucket_name
```

The base `application.yml` in the repo contains only environment variable placeholders. All secrets go in `application-local.yml` or as environment variables.

### 3. Run the Service

```bash
cd ingestion-service
mvn spring-boot:run -Dspring-boot.run.profiles=local
```

The service starts on `http://localhost:8080`.

### 4. Verify Startup

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/v1/documents
# Expected: 405 (Method Not Allowed — POST endpoint is registered)
```

---

## Testing the Pipeline

### Smoke Test — Single Upload

```bash
curl -v -X POST http://localhost:8080/api/v1/documents \
  -H "X-Tenant-ID: tenant-test-001" \
  -F "file=@/path/to/your/test.pdf;type=application/pdf"
```

Expected response:

```json
{
  "documentId": "9cabba37-0b64-4486-a58a-66f15d0df095",
  "status": "UPLOADED",
  "message": "Document successfully stored and queued for ML processing."
}
```

HTTP status: `202 Accepted`

### Verify the Pipeline End-to-End

**1. Document landed in PostgreSQL:**
```bash
docker exec -it lexguard-postgres psql -U your_db_user -d lexguard \
  -c "SELECT id, tenant_id, original_file_name, status, created_at FROM documents ORDER BY created_at DESC LIMIT 5;"
```

**2. Outbox event published:**
```bash
docker exec -it lexguard-postgres psql -U your_db_user -d lexguard \
  -c "SELECT id, event_type, status, retry_count FROM outbox_messages ORDER BY created_at DESC LIMIT 5;"
```

The `status` column should show `PUBLISHED` and `retry_count` should be `0` within 5 seconds of the upload.

**3. RabbitMQ received the message:**

Open `http://localhost:15672` (guest/guest) → Queues → `lexguard.document.parsing.queue`. The message count increments with each upload.

---

## API Reference

### POST `/api/v1/documents`

Accepts a PDF upload and queues it for asynchronous ML processing.

**Request**

| Part | Type | Required | Description |
|---|---|---|---|
| `file` | `multipart/form-data` | Yes | PDF binary (application/pdf only) |
| `X-Tenant-ID` | Header | Yes | Tenant identifier for data isolation |

**Response — 202 Accepted**

```json
{
  "documentId": "uuid",
  "status": "UPLOADED",
  "message": "Document successfully stored and queued for ML processing."
}
```

**Response — 503 Service Unavailable**

Returned when Cloudflare R2 is unreachable.

**Response — 400 Bad Request**

Returned when the file is missing, empty, or not a PDF.

---

## Known Limitations and Production TODOs

**Schema migrations:** `ddl-auto: update` is used for local development. Production requires Flyway with explicit migration scripts including the partial index for the outbox relay:

```sql
CREATE INDEX idx_outbox_pending ON outbox_messages (created_at) WHERE status = 'PENDING';
```

**Magic number validation:** The content-type check on upload uses the client-supplied MIME header. Production should inspect the first 4 bytes of the binary for the `%PDF` signature (`25 50 44 46`) or use Apache Tika.

**Quorum queues:** The RabbitMQ queue is declared as classic durable. Production clusters should use quorum queues (`x-queue-type: quorum`) for HA via Raft replication.

**Flyway dependency:** Add `spring-boot-starter-flyway` to `pom.xml` before production deployment.

---

## Document Processing Lifecycle

```
UPLOADED     →    PROCESSING    →    COMPLETED
   │                                     
   └──────────────────────────────→    FAILED
```

`UPLOADED` is set by this service. All subsequent transitions are owned by the Phase 2 Python ML workers via webhook or return queue callback.