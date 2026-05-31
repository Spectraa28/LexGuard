package com.lexguard.ingestion.model;

import java.time.Instant;
import java.util.UUID;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

@Entity
@Table(name = "documents")
public class Document {
    
    public enum DocumentStatus{
        UPLOADED, //safely in r2 , ml event queued
        PARSED,
        EMBEDDING,
        EMBEDDED, // chunks written to document_chunks, awaiting vector generation
        COMPLETED, // Ready for rag
        FAILED // pipeline crashed 
    }

    // ID is supplied externally from S3StorageProvider.StorageResult
// to guarantee the documentId in R2, the Document table, and the IngestionTaskEvent are identical
    @Id
    private UUID id;


    @Column(nullable = false,updatable = false)
    private String tenantId;

    @Column(nullable = false)
    private String originalFileName;

    @Column(nullable = false)
    private String storageKey;

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.NAMED_ENUM)
    @Column(name = "status" ,nullable = false)
    private DocumentStatus status;

  
    @Column(nullable = false)
    private boolean isLatest = true;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    private Instant updatedAt;


    protected Document(){}

    public Document(UUID id, String tenantId, String originalFileName, String storageKey){
        this.id = id;
        this.tenantId = tenantId;
        this.originalFileName = originalFileName;
        this.storageKey = storageKey;
        this.status = DocumentStatus.UPLOADED;
    }

    @PrePersist
    protected void onCreate(){
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    @PreUpdate
    protected void onUpdate(){
        this.updatedAt = Instant.now();
    }

    public UUID getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOriginalFileName() { return originalFileName; }
    public String getStorageKey() { return storageKey; }
    public DocumentStatus getStatus() { return status; }
    public boolean isLatest() { return isLatest; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    public void setStatus(DocumentStatus status) { this.status = status; }
    public void setLatest(boolean latest) { isLatest = latest; }

}
