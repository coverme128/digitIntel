# Deployment Environments

## local
- fixture data
- no broker live credentials
- deterministic test AI allowed

## staging
- real SEC
- real Massive
- IBKR paper
- isolated DB/object store

## shadow
- real data
- live opportunity generation
- no live execution

## production
- real data
- live broker account
- execution still user-confirmed

## Required Environment Flags

- `TRADING_MODE=disabled|paper|live`
- `AI_MODE=off|assist`
- `IR_FALLBACK_ENABLED=true|false`
- `MARKET_DATA_MODE=delayed|realtime`
- `ORDER_CONFIRMATION_REQUIRED=true`

Production invariant：
`ORDER_CONFIRMATION_REQUIRED=true`
