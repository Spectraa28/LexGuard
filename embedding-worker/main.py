import logging 
from fastapi import FastAPI , HTTPException
from pydantic import BaseModel , Field
from typing import List, Optional, Any, Dict
from sqlalchemy.exc import OperationalError

from retrieval import query_documents

logging.basicConfig(level=logging.INFO)
logger  = logging.getLogger("api")

app = FastAPI(title="Lexguard Retrieval API" , version="1.0")

class QueryRequest(BaseModel):
    query: str = Field(..., description="The search string or question to retrieve the context")
    limit: int  = Field(5, ge=1,le=50,description="Maximum number of chunks to return")
    
class ChunkMatch(BaseModel):
    document_id: str
    content: str
    score: float
    page_number: Optional[int] = None

class QueryResponse(BaseModel):
    results: List[ChunkMatch]
    

@app.post("/query",response_model=QueryResponse)
async def search_documents(request :QueryRequest):
    """Executes a vector search against embedded document chunks"""
    
    try:
        matches =query_documents(query_text=request.query, limit=request.limit)
        
        return QueryResponse(results=matches)
    
    except OperationalError as db_err:
        logger.error(f"Database connection dropped during vector : {db_err}")
        raise HTTPException(
            status_code=500,
            detail="Storage Backend is currently unavailable . Please try again later"
        )
        
    except Exception as e :
        logger.error(f"Unexpected Failure during document retrieval : {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occured while processing query"
        )
        