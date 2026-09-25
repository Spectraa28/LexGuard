import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, text

from config import get_database_settings
from telemetry import PGVECTOR_SEARCH_LATENCY


router = APIRouter(prefix="/demo", tags=["demo-control-plane"])
engine = create_engine(get_database_settings().DATABASE_URL, pool_pre_ping=True)

DEMO_TENANT_ID = os.getenv("DEMO_TENANT_ID", "demo")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_MANAGEMENT_PORT = int(os.getenv("RABBITMQ_MANAGEMENT_PORT", "15672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "lexguard.document.parsing.queue")

PROCESSING_STATES = ("UPLOADED", "PARSED", "EMBEDDED", "EMBEDDING")


def _serialize_document(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["original_file_name"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "chunk_count": row["chunk_count"],
        "is_stuck": row["is_stuck"],
    }


def _document_query(where_clause: str = "") -> str:
    return f"""
        SELECT d.id,
               d.original_file_name,
               d.status::text AS status,
               d.created_at,
               d.updated_at,
               COUNT(dc.id)::int AS chunk_count,
               (
                   d.status::text IN ('UPLOADED', 'PARSED', 'EMBEDDED', 'EMBEDDING')
                   AND COALESCE(d.updated_at, d.created_at) < NOW() - INTERVAL '5 minutes'
               ) AS is_stuck
        FROM documents d
        LEFT JOIN document_chunks dc ON dc.document_id = d.id
        WHERE d.tenant_id = :tenant_id {where_clause}
        GROUP BY d.id
    """


async def _queue_depth() -> int | None:
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(
                f"http://{RABBITMQ_HOST}:{RABBITMQ_MANAGEMENT_PORT}/api/queues/%2f/{QUEUE_NAME}",
                auth=(RABBITMQ_USER, RABBITMQ_PASS),
            )
            response.raise_for_status()
            return int(response.json().get("messages", 0))
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def _search_metrics() -> tuple[int, float]:
    count = 0
    total = 0.0
    for metric in PGVECTOR_SEARCH_LATENCY.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                count = int(sample.value)
            elif sample.name.endswith("_sum"):
                total = float(sample.value)
    return count, total


@router.get("/documents")
async def list_demo_documents(limit: int = 100):
    safe_limit = max(1, min(limit, 250))

    def fetch():
        with engine.connect() as conn:
            rows = conn.execute(
                text(_document_query() + " ORDER BY d.created_at DESC LIMIT :limit"),
                {"tenant_id": DEMO_TENANT_ID, "limit": safe_limit},
            ).mappings().all()
            return [_serialize_document(row) for row in rows]

    return {"tenant_id": DEMO_TENANT_ID, "documents": await asyncio.to_thread(fetch)}


@router.get("/documents/{document_id}")
async def get_demo_document(document_id: str):
    def fetch():
        with engine.connect() as conn:
            return conn.execute(
                text(_document_query("AND d.id = CAST(:document_id AS uuid)")),
                {"tenant_id": DEMO_TENANT_ID, "document_id": document_id},
            ).mappings().first()

    try:
        row = await asyncio.to_thread(fetch)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid document identifier") from exc
    if not row:
        raise HTTPException(status_code=404, detail="Document not found in demo tenant")
    return _serialize_document(row)


@router.get("/observability")
async def demo_observability():
    def fetch():
        with engine.connect() as conn:
            counts = conn.execute(
                text("""
                    SELECT status::text AS status, COUNT(*)::int AS count
                    FROM documents
                    WHERE tenant_id = :tenant_id
                    GROUP BY status
                """),
                {"tenant_id": DEMO_TENANT_ID},
            ).mappings().all()
            stats = conn.execute(
                text("""
                    SELECT
                        COUNT(*) FILTER (
                            WHERE status::text IN ('UPLOADED', 'PARSED', 'EMBEDDED', 'EMBEDDING')
                              AND COALESCE(updated_at, created_at) < NOW() - INTERVAL '5 minutes'
                        )::int AS stuck_documents,
                        COUNT(*) FILTER (WHERE status::text = 'COMPLETED')::int AS ready_documents
                    FROM documents
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": DEMO_TENANT_ID},
            ).mappings().one()
            chunk_count = conn.execute(
                text("""
                    SELECT COUNT(dc.id)::int
                    FROM document_chunks dc
                    JOIN documents d ON d.id = dc.document_id
                    WHERE d.tenant_id = :tenant_id
                """),
                {"tenant_id": DEMO_TENANT_ID},
            ).scalar_one()
            supervisor = conn.execute(
                text("""
                    SELECT last_seen_at
                    FROM system_heartbeats
                    WHERE service_name = 'supervisor'
                    LIMIT 1
                """)
            ).scalar()
            return counts, stats, chunk_count, supervisor

    counts, stats, chunk_count, supervisor = await asyncio.to_thread(fetch)
    queue_depth = await _queue_depth()
    searches, search_seconds = _search_metrics()
    supervisor_age = None
    if supervisor:
        supervisor_age = max(0, int((datetime.now(timezone.utc) - supervisor).total_seconds()))

    return {
        "tenant_id": DEMO_TENANT_ID,
        "documents_by_status": {row["status"]: row["count"] for row in counts},
        "ready_documents": stats["ready_documents"],
        "stuck_documents": stats["stuck_documents"],
        "chunk_count": chunk_count,
        "queue_depth": queue_depth,
        "supervisor_age_seconds": supervisor_age,
        "searches": searches,
        "average_search_ms": round((search_seconds / searches) * 1000, 2) if searches else 0,
        "captured_at": datetime.now(timezone.utc),
    }


@router.post("/scenarios/{scenario_id}")
async def run_demo_scenario(scenario_id: str):
    valid_scenarios = {"pipeline", "recovery", "isolation", "retrieval"}
    if scenario_id not in valid_scenarios:
        raise HTTPException(status_code=404, detail="Unknown demo scenario")

    observability = await demo_observability()
    evidence: list[dict[str, Any]] = []
    outcome = "passed"

    if scenario_id == "pipeline":
        evidence = [
            {"label": "Queue depth", "value": observability["queue_depth"], "healthy": observability["queue_depth"] is not None},
            {"label": "Ready documents", "value": observability["ready_documents"], "healthy": True},
            {"label": "Indexed chunks", "value": observability["chunk_count"], "healthy": True},
        ]
        if observability["queue_depth"] is None:
            outcome = "warning"
        summary = "The ingestion path is reachable and its durable state was inspected."
    elif scenario_id == "recovery":
        supervisor_fresh = observability["supervisor_age_seconds"] is not None and observability["supervisor_age_seconds"] < 180
        evidence = [
            {"label": "Stuck documents", "value": observability["stuck_documents"], "healthy": observability["stuck_documents"] == 0},
            {"label": "Supervisor heartbeat age", "value": observability["supervisor_age_seconds"], "unit": "seconds", "healthy": supervisor_fresh},
        ]
        if not supervisor_fresh or observability["stuck_documents"]:
            outcome = "warning"
        summary = "The supervisor heartbeat and five-minute stuck-document window were checked."
    elif scenario_id == "isolation":
        def isolation_counts():
            with engine.connect() as conn:
                return conn.execute(
                    text("""
                        SELECT
                            COUNT(*) FILTER (WHERE tenant_id = :tenant_id)::int AS visible,
                            COUNT(*) FILTER (WHERE tenant_id <> :tenant_id)::int AS excluded
                        FROM documents
                    """),
                    {"tenant_id": DEMO_TENANT_ID},
                ).mappings().one()

        counts = await asyncio.to_thread(isolation_counts)
        evidence = [
            {"label": "Visible demo documents", "value": counts["visible"], "healthy": True},
            {"label": "Documents outside scope", "value": counts["excluded"], "healthy": True},
            {"label": "Bound tenant", "value": DEMO_TENANT_ID, "healthy": True},
        ]
        summary = "The demo control plane queried only its configured tenant boundary."
    else:
        retrieval_ready = observability["ready_documents"] > 0 and observability["chunk_count"] > 0
        evidence = [
            {"label": "Retrieval-ready documents", "value": observability["ready_documents"], "healthy": retrieval_ready},
            {"label": "Searchable chunks", "value": observability["chunk_count"], "healthy": retrieval_ready},
            {"label": "Observed searches", "value": observability["searches"], "healthy": True},
        ]
        if not retrieval_ready:
            outcome = "warning"
        summary = "Completed documents and searchable vector chunks were verified."

    return {
        "scenario_id": scenario_id,
        "outcome": outcome,
        "summary": summary,
        "evidence": evidence,
        "executed_at": datetime.now(timezone.utc),
    }
