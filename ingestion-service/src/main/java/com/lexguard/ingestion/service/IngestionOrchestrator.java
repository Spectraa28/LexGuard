package com.lexguard.ingestion.service;


import com.lexguard.ingestion.service.S3StorageProvider;
import com.lexguard.ingestion.model.Document;
import com.lexguard.ingestion.model.DocumentUploadRequest;
import com.lexguard.ingestion.model.IngestionTaskEvent;
import com.lexguard.ingestion.service.persistence.DocumentPersistenceService;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@Service
public class IngestionOrchestrator {
    private final S3StorageProvider s3StorageProvider;
    private final DocumentPersistenceService documentPersistenceService;


    public IngestionOrchestrator(
        S3StorageProvider s3StorageProvider,
        DocumentPersistenceService documentPersistenceService
    ){
        this.s3StorageProvider = s3StorageProvider;
        this.documentPersistenceService = documentPersistenceService;
    }

    public UUID ingestDocument(MultipartFile file, String tenantId, DocumentUploadRequest request) {
        
        S3StorageProvider.StorageResult storageResult = s3StorageProvider.uploadDocument(file, tenantId);
        
        UUID documentId = UUID.fromString(storageResult.documentId());
        String originalFileName = file.getOriginalFilename() != null ? file.getOriginalFilename() : "untitled.pdf";

        Document document = new Document(
                documentId, 
                tenantId, 
                originalFileName, 
                storageResult.storageKey()
        );

        IngestionTaskEvent event = IngestionTaskEvent.create(
                documentId,
                storageResult.storageKey(),
                tenantId
        );

        
        documentPersistenceService.persistIngestion(document, event);

        return documentId;
    }

}
