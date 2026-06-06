package com.lexguard.ingestion.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexguard.ingestion.model.IngestionTaskEvent;
import com.lexguard.ingestion.model.OutboxMessage;
import com.lexguard.ingestion.repository.OutboxMessageRepository;



@Service
public class TransactionalOutboxService {
    private final OutboxMessageRepository outboxMessageRepository;
    private  final ObjectMapper objectMapper;

    public TransactionalOutboxService(
        OutboxMessageRepository outboxMessageRepository,
        ObjectMapper objectMapper
    ){
        this.outboxMessageRepository = outboxMessageRepository;
        this.objectMapper = objectMapper;
    }

    // Serializes the domain event and saves it to the outside table 
    @Transactional(propagation = Propagation.MANDATORY)
    public void saveEvent(IngestionTaskEvent event){
        try{
            // Converts the record to JSON

            String payload = objectMapper.writeValueAsString(event);

            //Forces the Pennding initial state via the entity factory method
            OutboxMessage message = OutboxMessage.createPending("DocumentIngested",payload , event.documentId().toString() );

            outboxMessageRepository.save(message);

        } catch (JsonProcessingException e){
            throw new IllegalStateException("Failed  to serialize IngestionTaskevent to json. Triggering Rollback. ",e);
        }
    }
}
