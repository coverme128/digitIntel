# Operations Runbook

## Daily Pre-market

- check SEC lag
- check last market-data timestamp
- check broker session
- reconcile portfolio
- inspect failed jobs
- inspect stale opportunities

## During Market

Monitor:
- stream health
- READY triggers
- broker reconciliation
- P0 alerts

## Post-market

- finalize daily bars
- recompute reaction windows
- update analog outcomes
- save daily portfolio snapshot
- replay failed SEC events

## Incident: SEC unavailable

- mark source DEGRADED
- retain previous state
- do not create READY from incomplete event
- backfill when restored

## Incident: Massive unavailable

- block reaction-dependent transitions
- do not infer prices from broker unless explicit fallback configured

## Incident: IBKR unavailable

- mark portfolio stale
- block execution
- do not change existing Opportunity facts

## Incident: Wrong Mapping

P0:
- stop affected security
- disable execution
- correct registry
- replay all affected events

## Backup

Daily:
- Postgres
- raw object inventory
- config/rule versions

Regular restore drill required.
