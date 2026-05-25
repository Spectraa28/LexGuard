package com.lexguard.ingestion.service.persistence;

import com.lexguard.ingestion.model.Document;
import com.lexguard.ingestion.model.IngestionTaskEvent;
import com.lexguard.ingestion.repository.DocumentRepository;
import com.lexguard.ingestion.service.TransactionalOutboxService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentPersistenceService {

    private final DocumentRepository documentRepository;
    private final TransactionalOutboxService outboxService;

    public DocumentPersistenceService(
            DocumentRepository documentRepository, 
            TransactionalOutboxService outboxService) {
        this.documentRepository = documentRepository;
        this.outboxService = outboxService;
    }
    
    @Transactional
    public void persistIngestion(Document document, IngestionTaskEvent event) {
        documentRepository.save(document);
        
        outboxService.saveEvent(event);
        
    }
}