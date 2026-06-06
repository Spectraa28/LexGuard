CREATE TABLE system_heartbeats (
    service_name VARCHAR(50) PRIMARY KEY,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL
);