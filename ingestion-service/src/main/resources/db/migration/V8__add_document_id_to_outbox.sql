DROP TABLE IF EXISTS outbox_messages;

-- 2. Recreate with the mandatory document_id field
CREATE TABLE outbox_messages (
    id UUID PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE,
    document_id VARCHAR(255) NOT NULL
);