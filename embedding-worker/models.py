import enum
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Boolean, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ENUM
from pgvector.sqlalchemy import Vector
import uuid

class DocumentStatus(enum.Enum):
    UPLOADED = "UPLOADED"
    PARSED = "PARSED"
    EMBEDDING = "EMBEDDING"
    EMBEDDED = "EMBEDDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        ENUM(DocumentStatus, name="document_status", create_type=False),
        nullable=False
    )
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # 1. The new schema column
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    chunks: Mapped[List["DocumentChunk"]] = relationship(
        back_populates="document", 
        cascade="all, delete-orphan"
    )

    # 2. The SQLAlchemy configuration hook
    __mapper_args__ = {
        "version_id_col": version
    }

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True,default=uuid.uuid4)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), 
        nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    chunk_type: Mapped[Optional[str]] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=text("CURRENT_TIMESTAMP")
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")
    embeddings: Mapped[List["ChunkEmbedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan"
    )

class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True,default=uuid.uuid4)
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False
    )
    embedding: Mapped[List[float]] = mapped_column(Vector(384), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )

    chunk: Mapped["DocumentChunk"] = relationship(back_populates="embeddings")
    

class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), 
        nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), 
        default="PENDING", 
        server_default=text("'PENDING'"), 
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=text("CURRENT_TIMESTAMP")
    )