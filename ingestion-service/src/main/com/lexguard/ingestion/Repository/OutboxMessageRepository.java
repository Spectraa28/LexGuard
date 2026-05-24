package com.lexguard.ingestion.repository;

import com.lexguard.ingestion.model.OutboxMessage;

import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;

import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.stereotype.Repository;

@Repository
public interface OutboxMessageRepository extends JpaRepository<OutboxMessage,UUID>{

    /**
     * Sweeps the outbox for pending message in strict FIFO order.
     * applies a pessimistic write lock to prevent multi pod race conditions 
     * explicity skipping already locked rowws to maximize relay throughput.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHint(@QueryHint(name = "jakarta.persistence.lock.timeout", value = "SKIP_LOCKED"))
    List<OutboxMessage> findbyStatusOrderByCreatedAtAsc(OutboxMessage.OutboxStatus status, Limit limit);
}
