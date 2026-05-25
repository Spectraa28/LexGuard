package com.lexguard.ingestion.service;

import com.lexguard.ingestion.model.OutboxMessage;
import com.lexguard.ingestion.repository.OutboxMessageRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class OutboxMessageRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxMessageRelay.class);
    private static final int MAX_RETRIES = 5;

    private final OutboxMessageRepository repository;
    private final RabbitEventPublisher publisher;

    public OutboxMessageRelay(
            OutboxMessageRepository repository, 
            RabbitEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    /**
     * Sweeps the database for pending events and pushes them to RabbitMQ.
     * Uses SKIP_LOCKED at the repository layer to allow safe multi-pod concurrency.
     */
    @Scheduled(fixedDelayString = "${lexguard.outbox.relay.delay:5000}")
    @Transactional
    public void processOutbox() {
        List<OutboxMessage> pendingMessages = repository.findPendingMessagesForUpdate();

        if (pendingMessages.isEmpty()) {
            return;
        }

        for (OutboxMessage message : pendingMessages) {
            boolean success = publisher.publish(message);

            if (success) {
                message.markPublished();
                log.debug("Successfully published outbox message: {}", message.getId());
            } else {
                message.markFailed(MAX_RETRIES);
                
                if (message.getStatus() == OutboxMessage.OutboxStatus.FAILED) {
                    log.error("Outbox message {} failed after {} retries. Marked as FAILED.", 
                            message.getId(), MAX_RETRIES);
                } else {
                    log.warn("Transient failure for outbox message {}. Retry {}/{}. Retrying later.", 
                            message.getId(), message.getRetryCount(), MAX_RETRIES);
                }
            }
        }
        
        // Transaction commits here, flushing all entity state changes back to PostgreSQL
        repository.saveAll(pendingMessages);
    }
}