# Core Output Contract

每个 Opportunity 的 CoreOutput 至少包含：

## Identity
- opportunity_id
- security_id
- ticker
- rule_version
- data_snapshot_version

## Event
- event_family
- event_type
- event_at
- role
- materiality

## Evidence
- source refs
- accession/document refs
- evidence spans
- evidence quality

## Facts
- normalized facts
- units
- periods
- fact versions

## Calculations
- fundamental deltas
- price reaction
- benchmark/sector adjusted metrics
- historical analog statistics

## Decision state
- state
- reason_codes
- trigger_status
- invalidation_status

## Entry / Invalidation
- entry conditions
- trigger progress
- invalidation rules
- invalidation status

## Portfolio
- portfolio snapshot
- exposure checks
- warnings
- hard blocks
- sizing worksheet

## Outcome
- linked position/trade
- MFE / MAE
- P&L when available

CoreOutput 不得把 AI 文本作为必需字段。
