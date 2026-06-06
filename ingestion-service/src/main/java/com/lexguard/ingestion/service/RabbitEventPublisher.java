package com.lexguard.ingestion.service;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import com.lexguard.ingestion.config.MessagingConfig;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import com.lexguard.ingestion.model.OutboxMessage;
import org.springframework.amqp.core.MessageProperties;

@Service
public class RabbitEventPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final String exchange;
    private final String routingKey;

    public RabbitEventPublisher(
            RabbitTemplate rabbitTemplate,
            @Value("${rabbitmq.exchange.ingestion:lexguard.ingestion.exchange}") String exchange,
            @Value("${rabbitmq.routing.key.document-ingested:document.ingested.key}") String routingKey) {
        this.rabbitTemplate = rabbitTemplate;
        this.exchange = exchange;
        this.routingKey = routingKey;
    }


    /*
    Pushing the payload to rabbitmq and wait synchronously for a publisher confirm
    */
   public boolean publish(OutboxMessage outboxMessage){
    Message message =  MessageBuilder
                .withBody(outboxMessage.getPayload().getBytes(StandardCharsets.UTF_8))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setMessageId(outboxMessage.getId().toString())
                .setCorrelationId((outboxMessage.getDocumentId()))
                .build();

    CorrelationData correlationData = new CorrelationData(outboxMessage.getId().toString());


    try {

        rabbitTemplate.send(
                    MessagingConfig.EXCHANGE_NAME, 
                    MessagingConfig.ROUTING_KEY, 
                    message, 
                    correlationData
            );
            // Block the relay thread for up to 5 seconds waiting for the brocket ACK
        CorrelationData.Confirm confirm = correlationData.getFuture().get(5,TimeUnit.SECONDS);
        return confirm != null && confirm.isAck();
    } catch (Exception e){
        return false;
    }
   }
}
