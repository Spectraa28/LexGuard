package com.lexguard.ingestion.model;

import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonProperty;

public record IngestionTaskEvent(
    @JsonProperty("eventId")
    UUID eventId,

    @JsonProperty("documentId")
    UUID documentId,

    @JsonProperty("storageKey")
    String storageKey,

    @JsonProperty("tenantId")
    String tenantId,

    @JsonProperty("occurredAt")
    Instant occuredAt
    ) {

        public static IngestionTaskEvent create(UUID documentID, String storageKey, String tenantId){
            return new IngestionTaskEvent(UUID.randomUUID(), documentID, storageKey, tenantId, Instant.now());
        }
}
