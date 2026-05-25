package com.lexguard.ingestion.model;


import org.springframework.web.multipart.MultipartFile;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record DocumentUploadRequest(

    @NotNull(message = "The document file must be provided in the multipart request payload")
    MultipartFile file,

    @NotBlank(message =  "Tenant Id is strictly required to guarantee downstream data")
    String tenantId
) {
     // TODO: replace MIME type header check with magic number validation (%PDF hex: 25 50 44 46)

// Client-controlled Content-Type header is insufficient as a security boundary 
    public DocumentUploadRequest {
        if (file  != null && file.isEmpty()){
            throw new IllegalArgumentException("The uploaded document contains zero bytes");
        }

        if(file != null && file.getContentType() != null && !file.getContentType().equals("application/pdf")){
            throw new IllegalArgumentException("lexguard only supports application/pdf file types");

        }
    }
}
