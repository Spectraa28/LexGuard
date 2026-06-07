CREATE TABLE users (
    id UUID PRIMARY KEY,
    tenant_name VARCHAR(255) NOT NULL,
    api_key_hash VARCHAR(64) NOT NULL UNIQUE,
    rate_limit_tier VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);