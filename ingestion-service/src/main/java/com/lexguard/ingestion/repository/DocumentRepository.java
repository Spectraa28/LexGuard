package com.lexguard.ingestion.repository;

import java.util.UUID;

import com.lexguard.ingestion.model.Document;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface DocumentRepository  extends JpaRepository<Document,UUID>{
    
}
