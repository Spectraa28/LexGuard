from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

@dataclass
class SearchResult:
    content: str
    page_number: Optional[int]
    distance: float

def retrieve_relevant_chunks(
    session: Session, 
    query_vector: List[float], 
    top_k: int = 5, 
    distance_threshold: float = 0.5
) -> List[SearchResult]:
    """
    Executes a vector similarity search against fully processed, active legal documents
    using a CTE to optimize vector casting and execution plan.
    """
    query = text("""
        WITH query_ctx AS (
            SELECT CAST(:query_vector AS vector) AS q_vec
        )
        SELECT 
            dc.content,
            dc.page_number,
            (ce.embedding <=> query_ctx.q_vec) AS distance
        FROM chunk_embeddings ce
        CROSS JOIN query_ctx
        JOIN document_chunks dc ON ce.chunk_id = dc.id
        JOIN documents d ON dc.document_id = d.id
        WHERE d.status = 'COMPLETED' 
          AND d.is_latest = true
          AND (ce.embedding <=> query_ctx.q_vec) < :distance_threshold
        ORDER BY distance ASC
        LIMIT :top_k;
    """)
    
    result_set = session.execute(
        query, 
        {
            "query_vector": str(query_vector),
            "distance_threshold": distance_threshold,
            "top_k": top_k
        }
    )
    
    return [
        SearchResult(
            content=row.content,
            page_number=row.page_number,
            distance=row.distance
        )
        for row in result_set
    ]