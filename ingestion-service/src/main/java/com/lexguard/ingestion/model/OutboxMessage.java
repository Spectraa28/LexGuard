package com.lexguard.ingestion.model;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "outbox_messages")
public class OutboxMessage {

    public enum OutboxStatus {
        PENDING,
        PUBLISHED,
        FAILED
    }

    @Id
    private UUID id;

    @Column(nullable = false, updatable = false)
    private String eventType;

    // Excellent addition for PostgreSQL JSONB mapping
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, updatable = false)
    private String payload;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OutboxStatus status; // Removed updatable = false so the Relay can modify it

    @Column(nullable = false)
    private int retryCount;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    private Instant processedAt;

    // Required by JPA
    protected OutboxMessage() {}

    private OutboxMessage(String eventType, String payload) {
        this.id = UUID.randomUUID();
        this.eventType = eventType;
        this.payload = payload;
        this.status = OutboxStatus.PENDING;
        this.retryCount = 0;
    }

    public static OutboxMessage createPending(String eventType, String payload) {
        return new OutboxMessage(eventType, payload);
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = Instant.now();
    }


    public void markPublished() {
        if (this.status != OutboxStatus.PENDING) {
            throw new IllegalStateException("Only pending messages can be marked as PUBLISHED.");
        }
        this.status = OutboxStatus.PUBLISHED;
        this.processedAt = Instant.now();
    }

    public void markFailed(int maxRetries) {
        if (this.status != OutboxStatus.PENDING) {
            throw new IllegalStateException("Only PENDING messages can transition to FAILED.");
        }
        
        this.retryCount++;
        
        if (this.retryCount >= maxRetries) {
            this.status = OutboxStatus.FAILED;
            this.processedAt = Instant.now();
        }
    }

    public UUID getId() { return id; }
    public String getEventType() { return eventType; }
    public String getPayload() { return payload; }
    public OutboxStatus getStatus() { return status; }
    public int getRetryCount() { return retryCount; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getProcessedAt() { return processedAt; }
}