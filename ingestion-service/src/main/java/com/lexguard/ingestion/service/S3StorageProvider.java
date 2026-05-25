package com.lexguard.ingestion.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

@Service
public class S3StorageProvider {
    
    public record StorageResult(String documentId, String storageKey) {}

    private final S3Client s3Client;
    private final String bucketName;

    public S3StorageProvider(
        S3Client s3Client,
        @Value("${cloudflare.r2.bucket-name}") String bucketName
    ){
        this.s3Client = s3Client;
        this.bucketName = bucketName;
    }

    /***
     * Streams the multipart file directly to Cloudflare R2 without fully loading 
     * it to the JVM memory, preventing OOM errors under heavy load.
     */
    public StorageResult uploadDocument(MultipartFile file, String tenantId) {
        String documentId = UUID.randomUUID().toString();
        String datePrefix = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy/MM/dd"));

        String storageKey = String.format("%s/%s/%s.pdf", tenantId, datePrefix, documentId);

        PutObjectRequest putObjectRequest = PutObjectRequest.builder()
                    .bucket(bucketName)
                    .key(storageKey)
                    .contentType("application/pdf")
                    .build();

        try {
            // Streams the bytes directly from embedded Tomcat buffer to R2
            s3Client.putObject(
                putObjectRequest,
                RequestBody.fromInputStream(file.getInputStream(), file.getSize())
            );
        } catch (IOException e) {
            throw new RuntimeException("Failed to read Document stream for R2 uploads", e);
        }            

        return new StorageResult(documentId, storageKey);
    }
}