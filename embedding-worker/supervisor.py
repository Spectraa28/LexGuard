import os 
import time 
import uuid 
import logging
from datetime import datetime , timezone , timedelta
from sqlalchemy import create_engine , select
from sqlalchemy.orm import Session, Mapped, mapped_column, exc
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from models import Document , DocumentStatus , OutboxEvent ,Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("supervisor")

SWEEP_INTERVAL = int(os.getenv("SWEEP_INTERVAL_SECONDS","60"))
TIMEOUT_THRESHOLD = int(os.getenv("STUCK_TIMEOUT_SECONDS","300"))
DATABSE_URL = os.getenv("DATABASE_URL")

def requeue_document(engine,doc_id:str,threshold_time: datetime):
    """
    Handles staate rollback and outbox insertion for a single document 
    executes in a completely isolated session to prevent N+1 
    """
    with Session(engine)  as session:
        try:
            doc = session.scalar(
                select(Document)
                .where(Document.id == doc_id)
                .where(Document.status.in_([
                    DocumentStatus.UPLOADED,
                    DocumentStatus.PARSED,
                    DocumentStatus.EMBEDDED,
                    DocumentStatus.EMBEDDING
                ]))
                .with_for_update(skip_locked=True)
            )
            
            # Maybesome other supervisor picked up by another supervisor or finished 
            if not doc:
                return
            
            last_active = doc.updated_at or doc.created_at
            if last_active >= threshold_time:
                return
            
            old_status = doc.status
            if doc.status == DocumentStatus.EMBEDDING:
                doc.status = DocumentStatus.PARSED
            elif doc.status == DocumentStatus.PARSED:
                doc.status = DocumentStatus.UPLOADED
            
            doc.updated_at = datetime.now(timezone.utc)
            
            event = OutboxEvent(document_id=doc.id)
            session.add(event)
            
            session.commit()
            logger.info(f"Re-queued document {doc.id} (Rollback { old_status.name} - > {doc.status.name})")
            
            
        except StaleDataError:
            logger.warning(f"Optimistic lock failure on document  {doc_id}, Skipping")
            session.rollback()
        except Exception as e:
            logger.error(f"Faailed to process  document {doc_id} : {e}")
            session.rollback()
            
def run_sweep(engine):
    """Main supervisor loop"""
    
    logger.info(f"Starting supervisor sweep . Inverval : {SWEEP_INTERVAL}s ,  timeout: {TIMEOUT_THRESHOLD}s")
    
    while True:
        try:
            threshold_time = datetime.now(timezone.utc) - timedelta(seconds=TIMEOUT_THRESHOLD)
            
            with Session(engine) as session:
                candidate_ids = session.scalars(
                    select(Document.id)
                    .where(
                        (Document.updated_at < threshold_time) |
                        ((Document.updated_at == None) & (Document.created_at < threshold_time))
                    )
                    .where(Document.status.in_([
                        DocumentStatus.UPLOADED,
                        DocumentStatus.PARSED,
                        DocumentStatus.EMBEDDED,
                        DocumentStatus.EMBEDDING
                    ]))
                ).all()
                
            if candidate_ids:
                logger.info(f" Sweep interval {len(candidate_ids)} potentially stucck documents ")
                
            for doc_id in candidate_ids:
                requeue_document(engine, doc_id,threshold_time)
                
        except Exception as e:
            logger.error(f"Sweep iteration failed : {e}")
            
        time.sleep(SWEEP_INTERVAL)
        
if __name__ == "__main__":
    engine = create_engine(DATABSE_URL)
    run_sweep(engine)