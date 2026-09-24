import os
import time
import tempfile
import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from sentence_transformers import SentenceTransformer

from models import Document, DocumentChunk,ChunkEmbedding, DocumentStatus
from config import get_worker_settings
from pdf_parser import parse_pdf

settings = get_worker_settings()

s3_client = boto3.client(
    's3',
    endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    region_name="auto" 
)

# PRELOADING EMBEDIING MODEL TO ENSURE THAT it doesnt load everytime a document comes 
MODEL_NAME ="all-MiniLM-L6-v2"
embedding_model = SentenceTransformer(MODEL_NAME)
# PARSED 
def process_PARSED(session: Session, document_id: str) -> str:
    """
    Handles R2 download and lightweight text-PDF chunking.
    Transition status from UPLOADED  -> PARSED -> EMBEDDING 
    """
    doc = session.get(Document, document_id)
    if not doc:
        return "FAILED"
    
    if doc.status == DocumentStatus.PARSED:
        return "SKIP_CLAIMED"
    if doc.status != DocumentStatus.UPLOADED:
        return "SKIP_STATE"
    
    try:
        doc.status = DocumentStatus.PARSED
        session.commit()
    except SQLAlchemyError as e:
        print(f"[Processor] Database error claiming PARSED state: {e}")
        session.rollback()
        return "NACK"
    
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            temp_path = tmp_file.name
            
        s3_client.download_file(settings.R2_BUCKET_NAME, doc.storage_key, temp_path)
            
        chunks = parse_pdf(temp_path)
        
    except (ClientError, EndpointConnectionError) as e:
        # Transient R2/Network Error -> Rollback to UPLOADED, Requeue
        print(f"[Processor] Transient R2/network error: {type(e).__name__}: {e}")
        time.sleep(5)
        session.rollback()
        doc.status = DocumentStatus.UPLOADED
        session.commit()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        return "NACK"
        
    except Exception as e:
        # TERMINAL ERROR -> Mark FAILED, Do NOT requeue
        print(f"[Processor] Terminal exception during PARSED: {type(e).__name__}: {e}")
        session.rollback()
        doc.status = DocumentStatus.FAILED # Must be FAILED to break the loop
        session.commit()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        return "FAILED" 
    
    try:
        db_chunks = []
        for i, chunk in enumerate(chunks):
            db_chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                page_number=chunk.page_number,
                chunk_type=chunk.chunk_type,
                content=chunk.content
            )
            db_chunks.append(db_chunk)
            
        session.add_all(db_chunks)
        doc.status = DocumentStatus.EMBEDDED
        session.commit()
        
    except SQLAlchemyError:
        session.rollback()
        raise
    
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            
    return "SUCCESS"

# EMBEDDING 
def process_embedding(session: Session, document_id: str) -> str:
    """
    Handles embedding generation for chunks.
    Transitions status from EMBEDDED -> EMBEDDING -> COMPLETED 
    using optimistic locking to prevent double-execution.
    """
    doc = session.get(Document, document_id)
    if not doc:
        return "FAILED"
    
    if doc.status == DocumentStatus.COMPLETED:
        return "SKIP_STATE"
    if doc.status != DocumentStatus.EMBEDDED:
        return "SKIP_STATE"
    
    # 1. First Version Check: Claiming the lock
    try:
        doc.status = DocumentStatus.EMBEDDING
        session.commit()
    except StaleDataError:
        print(f"[Processor] Lock claim failed: Document {document_id} was modified by another process.")
        session.rollback()
        return "SKIP_SUPERSEDED"
    except SQLAlchemyError as e:
        print(f"[Processor] Database error claiming EMBEDDING state: {e}")
        session.rollback()
        return "NACK"
    
    # 2. Expensive Computation
    try:
        chunks = sorted(doc.chunks, key=lambda c: c.chunk_index)
        
        if not chunks:
            doc.status = DocumentStatus.COMPLETED
            session.commit()
            return "SUCCESS"
        
        texts = [chunk.content for chunk in chunks]
        vectors = embedding_model.encode(texts)
        
        db_embeddings = []
        for chunk, vector in zip(chunks, vectors):
            db_embedding = ChunkEmbedding(
                chunk_id=chunk.id,
                embedding=vector.tolist(),
                model_name=MODEL_NAME
            )
            db_embeddings.append(db_embedding)
            
        session.add_all(db_embeddings)
        doc.status = DocumentStatus.COMPLETED
        
        # 3. Final Version Check: Committing the vectors
        try:
            session.commit()
        except StaleDataError:
            print(f"[Processor] Terminal write failed: Document {document_id} was superseded during embedding.")
            session.rollback()
            return "SKIP_SUPERSEDED"
            
        return "SUCCESS"
    
    except Exception as e:
        print(f"[Processor] Terminal exception during embedding: {type(e).__name__}: {e}")
        session.rollback()
        doc.status = DocumentStatus.FAILED
        session.commit()
        return "FAILED"
