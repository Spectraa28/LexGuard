package com.lexguard.ingestion.controller.advice;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import software.amazon.awssdk.services.s3.model.S3Exception;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * Maps AWS/Network failures to a 503 Service Unavailable.
     * This tells the client "We are temporarily down, try again later."
     */
    @ExceptionHandler(S3Exception.class)
    public ResponseEntity<ErrorResponse> handleStorageFailures(S3Exception ex) {
        log.error("Storage network failure: {}", ex.getMessage(), ex);
        
        ErrorResponse response = new ErrorResponse(
                HttpStatus.SERVICE_UNAVAILABLE.value(),
                "Service Unavailable",
                "The storage system is currently unreachable. Please try again later.",
                Instant.now()
        );
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(response);
    }

    /**
     * Maps @Valid validation failures to a 400 Bad Request.
     * Extracts the specific field errors so the frontend knows exactly what to highlight.
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidationExceptions(MethodArgumentNotValidException ex) {
        Map<String, String> errors = new HashMap<>();
        ex.getBindingResult().getFieldErrors().forEach(error -> 
                errors.put(error.getField(), error.getDefaultMessage())
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errors);
    }

    // Standardized Error DTO
    public record ErrorResponse(int status, String error, String message, Instant timestamp) {}
}