package com.lexguard.ingestion.model;

import java.time.Instant;
import java.util.UUID;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "outbox_message")
public class OutboxMessage {
   public enum OutboxStatus {
    PENDING,
    PUBLISHED,
    FAILED
   } 

   @Id
   @GeneratedValue(strategy = GenerationType.UUID)
   private UUID id;

   @Column(nullable = false, updatable = false)
   private String eventType;

   @JdbcTypeCode(SqlTypes.JSON)
   @Column(nullable = false, updatable = false)
   private String payload;

   @Column(nullable = false,updatable = false)
   private OutboxStatus status;

   protected OutboxMessage() {}

   private OutboxMessage(String eventType, String payload){
    this.eventType = eventType;
    this.payload = payload;
    this.createdAt  = Instant.now();
    this.status = OutboxStatus.PENDING;
   }


   public static OutboxMessage createPending(String eventType, String payload){
    return new OutboxMessage(eventType,payload);
   }

   public UUID getId() { return id; }
    public String getEventType() { return eventType; }
    public String getPayload() { return payload; }
    public Instant getCreatedAt() { return createdAt; }
    public OutboxStatus getStatus() { return status; }

    public void markPublished(){
        if (this.status != OutboxStatus.PENDING){
            throw new IllegalStateException("Onlu pending message can be  marked as Published")
        }
        this.status = OutboxStatus.PUBLISHED;
    }

    public void markFailed() {
        if (this.status != OutboxStatus.PENDING) {
            throw new IllegalStateException("Only PENDING messages can transition to FAILED. Domain processing failures must be handled by downstream DLQs.");
        }
        this.status = OutboxStatus.FAILED;
    }
}
