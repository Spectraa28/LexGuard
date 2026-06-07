import logging
import sys
import time
import asyncio
from contextvars import ContextVar
from typing import Optional
from functools import wraps

from prometheus_client import Histogram, Gauge


correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)

class CorrelationIdFilter(logging.Filter):
    """Injects the async context correlation ID into log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        cid = correlation_id_var.get()
        record.correlation_id = cid if cid else "SYSTEM"
        return True

def setup_logging(level: int = logging.INFO) -> None:
    """Configures the root logger. Must be called first in process lifespan."""
    root_logger = logging.getLogger()
    
    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s [trace:%(correlation_id)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())
    root_logger.addHandler(handler)
    
    # Silence noisy dependencies
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pika").setLevel(logging.WARNING)


PGVECTOR_SEARCH_LATENCY = Histogram(
    name="pgvector_search_latency_seconds",
    documentation="Latency of pgvector similarity search queries",
    buckets=(0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0)
)

STUCK_DOCUMENT_COUNT = Gauge(
    "lexguard_stuck_document_count", 
    "Current number of documents stuck in intermediate processing states"
)

LAST_SUPERVISOR_SWEEP_TIMESTAMP = Gauge(
    "lexguard_last_supervisor_sweep_timestamp_seconds", 
    "UNIX timestamp of the most recent successful supervisor sweep"
)

RABBITMQ_QUEUE_DEPTH = Gauge(
    "lexguard_rabbitmq_queue_depth", 
    "Number of messages currently waiting in the worker queue"
)


def track_search_latency(func):
    """Records execution time directly into the pgvector Histogram."""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        with PGVECTOR_SEARCH_LATENCY.time():
            return await func(*args, **kwargs)
            
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        with PGVECTOR_SEARCH_LATENCY.time():
            return func(*args, **kwargs)
            
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper