package com.lexguard.ingestion.controller;

import com.lexguard.ingestion.model.DocumentUploadRequest;
import com.lexguard.ingestion.service.IngestionOrchestrator;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.net.URI;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/documents")
public class DocumentIngestionController {

    private final IngestionOrchestrator ingestionOrchestrator;

    public DocumentIngestionController(IngestionOrchestrator ingestionOrchestrator) {
        this.ingestionOrchestrator = ingestionOrchestrator;
    }

    /**
     * Accepts a PDF upload and queues it for asynchronous ML processing.
     * @param file The binary PDF payload.
     * @param tenantId The multi-tenant boundary, strictly enforced via HTTP headers.
     * @param request Additional JSON metadata. Validated before method execution.
     */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<IngestionResponse> uploadDocument(
            @RequestParam("file") MultipartFile file,
            @RequestHeader("X-Tenant-ID") String tenantId,
            @Valid @RequestPart(value = "metadata", required = false) DocumentUploadRequest request) {

        // The orchestrator handles the S3 upload and the ACID dual-write.
        UUID documentId = ingestionOrchestrator.ingestDocument(file, tenantId, request);

        IngestionResponse response = new IngestionResponse(
                documentId,
                "UPLOADED",
                "Document successfully stored and queued for ML processing."
        );

        return ResponseEntity
                .accepted()
                .location(URI.create("/api/v1/documents/" + documentId))
                .body(response);
    }

    public record IngestionResponse(UUID documentId, String status, String message) {}
}