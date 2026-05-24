package com.lexguard.ingestion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class LexGuardIngestionApplication {

    public static void main(String[] args) {
        SpringApplication.run(LexGuardIngestionApplication.class, args);
    }
}