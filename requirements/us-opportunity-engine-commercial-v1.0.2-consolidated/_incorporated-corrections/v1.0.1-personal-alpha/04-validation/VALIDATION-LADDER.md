# Validation Ladder

## Stage 1 — Historical Replay

Goal:
- code correctness
- rule sanity
- no look-ahead

Exit:
`HISTORICAL_REPLAY_READY`

## Stage 2 — Shadow

Minimum:
- 20 trading days

No orders.

Measure:
- event coverage
- qualified opportunities
- WATCH/READY transitions
- invalidations
- hypothetical outcomes
- missed opportunities
- false positives

Exit:
`SHADOW_READY`

## Stage 3 — Paper Trading

Measure:
- actual order mechanics
- slippage
- partial fills
- state/order reconciliation
- stop/invalidation workflow

Exit:
`PAPER_TRADING_READY`

## Stage 4 — Small Capital Live

Purpose:
- validate behavior under real money
- validate fills/fees/emotions/process

Rules:
- use conservative risk defaults
- no automatic scale-up
- minimum 30 completed live trades before material rule conclusion
- family-level conclusions require adequate sample

Exit is not “profitable once”.
Exit requires process/reliability gates.
