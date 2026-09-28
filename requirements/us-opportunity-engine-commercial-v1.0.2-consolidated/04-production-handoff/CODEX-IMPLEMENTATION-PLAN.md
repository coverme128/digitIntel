# Codex Implementation Plan

## Phase 0 — Contract Freeze

Codex 先读取：
1. MASTER-CONTRACT
2. 02-domain-rules/*
3. 03-implementation/DATA-MODEL

输出：
- conflicts
- implementation gaps
- proposed migrations

不得直接改 domain semantics。

## Phase 1 — Foundation

交付：
- monorepo/app structure
- Postgres migrations
- Redis/BullMQ
- MinIO/S3
- security registry
- source registry
- audit tables
- test harness

Gate：
`FOUNDATION_READY`

## Phase 2 — SEC Truth Pipeline

交付：
- submissions
- filing fetch
- exhibit fetch
- companyfacts
- raw immutable storage
- evidence mapping

Gate：
`SEC_CANONICAL_READY`

## Phase 3 — Market Data

交付：
- Massive historical
- realtime minute aggregates
- market calendar
- benchmark mapping
- reaction calculator

Gate：
`REACTION_ENGINE_READY`

## Phase 4 — Domain Engines

交付：
- event classifier
- materiality
- fundamental deltas
- reaction buckets
- opportunity gates
- state machine
- invalidation

Gate：
`OPPORTUNITY_ENGINE_READY`

## Phase 5 — Portfolio

先 read-only：
- IBKR auth
- account
- positions
- reconciliation
- exposure

Gate：
`PORTFOLIO_READ_READY`

## Phase 6 — UX

按 Product Spec：
- Today
- Detail
- Watchlist
- Portfolio
- History
- Evidence drawer

Gate：
`PRODUCT_BASELINE_READY`

## Phase 7 — AI

接入：
- extraction helper
- comparison
- explanation

AI 不得成为 blocker：
- AI failure 时保留 deterministic path
- 缺少必需字段则 REVIEW_REQUIRED

Gate：
`AI_ASSIST_READY`

## Phase 8 — Shadow

20 trading days。

输出：
- coverage
- missed events
- false positives
- data gaps
- rule defects

Gate：
`SHADOW_READY`

## Phase 9 — IBKR Paper

- order intent
- confirmation
- paper order
- execution reconciliation

Gate：
`PAPER_TRADING_READY`

## Phase 10 — Production

只有 Release Gates 全过：
`COMMERCIAL_V1_READY`

否则必须明确 blocker。
