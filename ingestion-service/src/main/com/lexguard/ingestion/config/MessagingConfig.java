package com.lexguard.ingestion.config;


import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.fasterxml.jackson.databind.ObjectMapper;

@Configuration
public class MessagingConfig {

    public static final String EXCHANGE_NAME = "lexguard.ingestion.exchange";
    public static final String QUEUE_NAME  = "lexguard.document.parsing.queue";
    public static final String ROUTING_KEY = "document.ingestion.routing.key";

    @Bean
    public Jackson2JsonMessageConverter jackson2JsonMessageConverter(ObjectMapper objectMapper){
        return new Jackson2JsonMessageConverter(objectMapper);
    }

    @Bean
    public DirectExchange ingestionExchange(){
        return new DirectExchange(EXCHANGE_NAME, true, false);
    }

    @Bean 
    public  Queue documentParsingQueue() {
        return new Queue(QUEUE_NAME,true);
    }

    @Bean
    public Binding binding(Queue documentParsingQueue, DirectExchange ingestionExchange){
        return BindingBuilder
                    .bind(documentParsingQueue)
                    .to(ingestionExchange)
                    .with(ROUTING_KEY);
    }
}