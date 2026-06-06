from dataclasses import dataclass
from typing import List, Optional ,Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text ,create_engine
from sentence_transformers import SentenceTransformer
from config import settings

MODEL_NAME = "all-MiniLM-L6-v2"
embedding_model = SentenceTransformer(MODEL_NAME)
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

@dataclass
class SearchResult:
    document_id: str
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
            d.id AS document_id,
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
            document_id=str(row.document_id),
            content=row.content,
            page_number=row.page_number,
            distance=row.distance
        )
        for row in result_set
    ]
    


def query_documents(query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    The Orchestrator: Bridges the FastAPI endpoint and the database search.
    Handles text embedding, session management, and score translation.
    """
    # Mismatch 2 fix: Convert raw API text into a 384-dimensional vector
    query_vector = embedding_model.encode(query_text).tolist()
    
    # Execute the database search
    with Session(engine) as session:
        raw_results = retrieve_relevant_chunks(
            session=session,
            query_vector=query_vector,
            top_k=limit
        )
        
    # Mismatch 3 fix: Translate distance to score, and format for Pydantic
    formatted_matches = []
    for result in raw_results:
        # For cosine distance, similarity score is (1.0 - distance)
        similarity_score = 1.0 - result.distance
        
        formatted_matches.append({
            "document_id": result.document_id,
            "content": result.content,
            "score": round(similarity_score, 4),
            "page_number": result.page_number
        })
        
    return formatted_matches