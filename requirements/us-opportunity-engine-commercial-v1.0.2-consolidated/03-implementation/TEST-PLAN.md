# Test Plan

## Unit

- CIK/ticker mapping
- period normalization
- margin bps calculation
- guidance midpoint
- buyback / market cap
- dilution %
- market-session mapping
- benchmark excess return
- state transitions
- sizing worksheet

## Contract Tests

SEC:
- submissions schema
- filing document resolution
- XBRL fixture parsing

Massive:
- minute bar
- realtime timestamp
- historical backfill

IBKR:
- account
- positions
- order preview
- paper execution

## Golden Fixtures

至少准备：
- 10 earnings/guidance
- 5 buyback
- 5 insider purchase
- 5 activist 13D
- 5 financing/dilution
- 5 material events
- 5 M&A/special

每个 fixture 必须保存：
- source refs
- expected event
- expected facts
- expected calculations
- expected state range

## Regression

规则升级必须重放 Golden Fixtures。

## Shadow Test

至少 20 个交易日：
- 不下单
- 每日生成机会
- 保存 trigger
- 保存 hypothetical outcome
- 检查 false positives / missing events

## Paper Trading

至少：
- order intent
- confirm
- submit
- execution reconcile
- cancel
- reject
- partial fill
