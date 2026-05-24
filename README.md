# LexGuard: AI Observability & Legal Inference

## The Problem
Enterprise legal teams review thousands of contracts annually at $200 to $500 per attorney hour. Yet, they cannot deploy AI for automated auditing because a single LLM hallucination on a liability clause creates unacceptable corporate risk. 

LexGuard solves this adoption blocker by wrapping a strict legal extraction engine inside a real-time observability platform. It mathematically proves that every generated insight is strictly faithful to the source PDF, actively intercepts semantic drift, and leverages a tiered caching architecture to execute multi-million token context windows at a fraction of standard API costs.

## Architecture

```text
[Client (Next.js)]
       │
       ▼
[Phase 1: Ingestion Pipeline (Spring Boot)] ──(RabbitMQ)──► [OCR & Lineage] ──► [PgVector]
       │
       ▼
[Phase 2: Guardrailed Inference (FastAPI)] ──► [Llama Guard (Input Shield)]
       │
       ├──► (Cache Hit: 50x Cost Drop) ──► [Semantic Cache] ──► (Return)
       │
       ├──► (L1: Fast Extraction) ───────► [DeepSeek-V3] ──► (Strict JSON Return)
       │
       └──► (L2 Fallback / Circuit Breaker) ─► [DeepSeek-R1] ──► (Deep Reasoning Return)
       │
       ▼
[Phase 3: Observability Control (Background)] ──► [DeBERTa (Faithfulness)] ──► [PostgreSQL (Audit Log)] ──► [Grafana]
