import re
import uuid
import hashlib
import httpx
import logging
import asyncio
from typing import List, Optional, Any, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text, create_engine
from sqlalchemy.exc import OperationalError

from telemetry import setup_logging, correlation_id_var, track_search_latency
from retrieval import query_documents
from config import settings
from telemetry import STUCK_DOCUMENT_COUNT, RABBITMQ_QUEUE_DEPTH, LAST_SUPERVISOR_SWEEP_TIMESTAMP

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

class AuthenticatedUser(BaseModel):
    id: str
    tenant_name: str
    rate_limit_tier: str

async def get_api_key_user(
    request: Request,
    api_key: str = Security(api_key_header)
) -> AuthenticatedUser:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def fetch_user_from_db():
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, tenant_name, rate_limit_tier 
                    FROM users 
                    WHERE api_key_hash = :hash 
                    AND is_active = true
                """),
                {"hash": api_key_hash}
            ).fetchone()
            return result

    loop = asyncio.get_running_loop()
    user_row = await loop.run_in_executor(None, fetch_user_from_db)

    if not user_row:
        raise HTTPException(status_code=401, detail="Invalid or inactive API Key")

    user = AuthenticatedUser(
        id=str(user_row[0]),
        tenant_name=user_row[1],
        rate_limit_tier=user_row[2]
    )
    request.state.user = user
    return user


def tenant_key_func(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "tenant_name"):
        return user.tenant_name
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"

limiter = Limiter(key_func=tenant_key_func)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting LexGuard Retrieval API...")
    yield
    logger.info("Shutting down LexGuard Retrieval API...")


app = FastAPI(title="Lexguard Retrieval API", version="1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

engine = create_engine(settings.DATABASE_URL)


@app.exception_handler(RequestValidationError)
async def security_validation_exception_handler(request: Request, exc: RequestValidationError):
    for error in exc.errors():
        if "Security Policy Violation" in error.get("msg", ""):
            return JSONResponse(status_code=403, content={"detail": "Request blocked by security policy."})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    incoming_id = request.headers.get("X-Correlation-ID")
    trace_id = incoming_id if incoming_id else str(uuid.uuid4())
    token = correlation_id_var.set(trace_id)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = trace_id
        return response
    finally:
        correlation_id_var.reset(token)

app.mount("/metrics/", make_asgi_app())


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="The search string or question to retrieve the context")
    limit: int = Field(5, ge=1, le=50, description="Maximum number of chunks to return")

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Query must contain at least 3 non-whitespace characters.")
        if re.search(r'[\x00-\x1F\x7F]', v):
            raise ValueError("Query contains invalid control characters.")
        llm_control_pattern = r'(<\|.*?\|>|<<SYS>>|\[/?INST\])'
        if re.search(llm_control_pattern, v, flags=re.IGNORECASE):
            raise ValueError("Security Policy Violation: Forbidden system tokens detected.")
        return v

class ChunkMatch(BaseModel):
    document_id: str
    content: str
    score: float
    page_number: Optional[int] = None

class QueryResponse(BaseModel):
    results: List[ChunkMatch]
    
    
    
@app.get("/health", response_model=Dict[str, Any])
async def health_check(response: Response):
    loop = asyncio.get_running_loop()
    health_state = {
        "status": "healthy",
        "database": "down",
        "rabbitmq": "down",
        "pipeline": {"stuck_documents": None, "last_supervisor_sweep_unix": None, "queue_depth": None}
    }
    is_degraded = False

    def run_db_checks():
        with engine.connect() as conn:
            stuck = conn.execute(text(
                "SELECT COUNT(*) FROM documents WHERE status IN ('PARSED', 'EMBEDDING') "
                "AND updated_at < NOW() - INTERVAL '10 minutes'"
            )).scalar()
            sweep = conn.execute(text(
                "SELECT EXTRACT(EPOCH FROM last_seen_at) FROM system_heartbeats WHERE service_name = 'supervisor' LIMIT 1"
            )).scalar()
            return stuck, sweep

    try:
        stuck_docs, last_sweep = await loop.run_in_executor(None, run_db_checks)
        logger.info(f"DEBUG sweep value: {last_sweep} type: {type(last_sweep)}")
        health_state["pipeline"].update({"stuck_documents": stuck_docs, "last_supervisor_sweep_unix": last_sweep})
        health_state["database"] = "up"

        # Update Prometheus Gauges from real database state
        STUCK_DOCUMENT_COUNT.set(stuck_docs or 0)
        if last_sweep:
            LAST_SUPERVISOR_SWEEP_TIMESTAMP.set(float(last_sweep))

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        is_degraded = True

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            # TODO: Move credentials to config.py
            rmq_resp = await client.get(
                "http://rabbitmq:15672/api/queues/%2f/lexguard.document.parsing.queue",
                auth=("guest", "guest")
            )
            rmq_resp.raise_for_status()
            queue_depth = rmq_resp.json().get("messages", 0)
            health_state["pipeline"]["queue_depth"] = queue_depth
            health_state["rabbitmq"] = "up"

            # Update RabbitMQ Gauge
            RABBITMQ_QUEUE_DEPTH.set(queue_depth)

    except Exception as e:
        logger.error(f"RabbitMQ health check failed: {e}")
        is_degraded = True

    if is_degraded:
        health_state["status"] = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_state


@app.post("/query", response_model=QueryResponse)
@limiter.limit("60/minute")
@track_search_latency
async def search_documents(
    request: Request,
    query_payload: QueryRequest,
    user: AuthenticatedUser = Depends(get_api_key_user)
):
    try:
        loop = asyncio.get_running_loop()
        # TODO: Phase 3 - pass user.tenant_name for data isolation
        matches = await loop.run_in_executor(
            None,
            query_documents,
            query_payload.query,
            query_payload.limit
        )
        return QueryResponse(results=matches)
    except OperationalError as db_err:
        logger.error(f"Database connection dropped: {db_err}")
        raise HTTPException(status_code=503, detail="Storage Backend unavailable")
    except Exception as e:
        logger.error(f"Unexpected Failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
    
    
@app.post("/demo/query", response_model=QueryResponse)
@limiter.limit("10/minute")
@track_search_latency
async def demo_search(request: Request, query_payload: QueryRequest):
    """
    Public demo endpoint. No API key required.
    Rate limited to 10 requests/minute per IP.
    """
    try:
        loop = asyncio.get_running_loop()
        matches = await loop.run_in_executor(
            None,
            query_documents,
            query_payload.query,
            query_payload.limit
        )
        return QueryResponse(results=matches)
    except OperationalError as db_err:
        logger.error(f"Database connection dropped: {db_err}")
        raise HTTPException(status_code=503, detail="Storage Backend unavailable")
    except Exception as e:
        logger.error(f"Unexpected Failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")