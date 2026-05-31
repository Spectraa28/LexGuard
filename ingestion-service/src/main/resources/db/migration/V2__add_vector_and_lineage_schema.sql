-- 1. Enable the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create the Status ENUM
CREATE TYPE document_status AS ENUM (
    'UPLOADED',
    'PARSED',
    'EMBEDDED',
    'COMPLETED',
    'FAILED'
);

-- 3. Retrofit the documents Table (New Column)
ALTER TABLE documents 
    ADD COLUMN is_latest BOOLEAN NOT NULL DEFAULT true;

-- 4. Retrofit the documents Table (State Machine)
ALTER TABLE documents 
    ALTER COLUMN status TYPE document_status 
    USING status::text::document_status;

-- 5. Create document_lineage
CREATE TABLE document_lineage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    child_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    amendment_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_parent_document UNIQUE (parent_document_id)
);

-- 6. Index document_lineage
CREATE INDEX idx_lineage_child ON document_lineage (child_document_id);

-- 7. Create document_chunks
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    chunk_type VARCHAR(50),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. Index document_chunks
CREATE INDEX idx_chunks_document_id ON document_chunks (document_id);
CREATE INDEX idx_chunks_document_index ON document_chunks (document_id, chunk_index);

-- 9. Create chunk_embeddings
CREATE TABLE chunk_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_chunk_model UNIQUE (chunk_id, model_name)
);

-- 10. Build the HNSW Index
CREATE INDEX idx_chunk_embeddings_hnsw ON chunk_embeddings 
    USING hnsw (embedding vector_cosine_ops) 
    WITH (m = 16, ef_construction = 128);