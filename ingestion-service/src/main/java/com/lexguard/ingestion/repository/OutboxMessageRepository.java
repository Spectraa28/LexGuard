package com.lexguard.ingestion.repository;

import com.lexguard.ingestion.model.OutboxMessage;
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface OutboxMessageRepository extends JpaRepository<OutboxMessage, UUID> {

    /**
     * Grabs a batch of pending messages. 
     * FOR UPDATE locks the rows so other threads can't read them.
     * SKIP LOCKED instantly skips rows already locked by other relay pods.
     */
    @Query(value = """
            SELECT * FROM outbox_messages 
            WHERE status = 'PENDING' 
            ORDER BY created_at ASC 
            LIMIT 10 
            FOR UPDATE SKIP LOCKED
            """, nativeQuery = true)
    List<OutboxMessage> findPendingMessagesForUpdate();
    
    /**
     * Sweeps the outbox for pending message in strict FIFO order.
     * applies a pessimistic write lock to prevent multi pod race conditions 
     * explicity skipping already locked rows to maximize relay throughput.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints({
        @QueryHint(name = "jakarta.persistence.lock.timeout", value = "-2")
    })
    List<OutboxMessage> findByStatusOrderByCreatedAtAsc(OutboxMessage.OutboxStatus status, Limit limit);
}