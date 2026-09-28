# Data Source Contracts

## SEC

Base capabilities:
- submissions history
- XBRL company facts
- filing documents
- exhibits

Requirements:
- identify with compliant User-Agent
- respect SEC fair access
- immutable raw copy
- accession number canonical key
- accepted timestamp preserved

Failure:
- retry with backoff
- never fabricate
- source state = DEGRADED

## Massive

Roles:
- historical OHLCV
- minute aggregates
- realtime aggregates/trades/quotes as subscribed
- corporate actions as required

Requirements:
- raw event timestamp
- exchange/session awareness
- adjusted/unadjusted policy explicit
- no silent mix of delayed/realtime

Failure:
- mark reaction incomplete
- block READY when required window incomplete

## IBKR

Roles:
- account
- positions
- PnL
- orders
- executions
- optional market-data fallback

V1 defaults:
- read-only first
- paper trading before live
- live order requires explicit confirmation

## Company IR

Role:
- supplemental official evidence only

Rules:
- only official domain
- source registry per company/domain
- cache original
- PDF/HTML hash
- if inaccessible, do not replace with random web result
