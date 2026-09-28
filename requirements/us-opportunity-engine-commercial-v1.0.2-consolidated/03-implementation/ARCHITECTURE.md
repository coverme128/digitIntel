# Architecture

## Recommended Stack

- Frontend: Next.js / TypeScript
- API: TypeScript service
- DB: PostgreSQL
- Queue: Redis + BullMQ
- Object storage: MinIO / S3 compatible
- Scheduler: job scheduler with market calendar support
- AI Gateway: provider-agnostic
- Metrics: OpenTelemetry + Prometheus-compatible backend
- Logs: structured JSON
- Secrets: environment/secret manager

## Services

### source-sec
- submissions feed
- filing fetch
- exhibit fetch
- XBRL fetch

### source-market
- Massive REST
- Massive WebSocket
- historical backfill

### source-broker
- IBKR account
- positions
- orders
- executions

### source-ir
- fallback fetcher
- per-domain adapter
- HTML/PDF capture

### normalization
- security registry
- filing normalization
- metric normalization

### event-engine
- event classification
- materiality

### fundamental-engine
- period alignment
- delta calculations

### reaction-engine
- session mapping
- benchmark/sector reaction

### opportunity-engine
- gates
- states
- invalidation

### portfolio-engine
- reconciliation
- exposure
- risk gates

### presentation
- deterministic summaries
- AI explanations

## Storage Layers

Raw:
- exact source payload/doc

Canonical:
- normalized records

Derived:
- calculations

Presentation:
- user-facing text

禁止直接从 AI 输出写入 Canonical。
