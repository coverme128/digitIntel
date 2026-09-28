# Release Gates

## G01 Data Identity
- ticker/CIK/security mapping 100% golden pass

## G02 SEC Integrity
- accession dedup pass
- accepted timestamp pass
- raw hash saved

## G03 Evidence
- all material facts link to evidence
- zero orphan critical fact

## G04 Financial Reconciliation
- key metrics reconcile with filing/exhibit fixtures

## G05 Market Reaction
- session mapping tests pass
- benchmark series complete
- no silent delayed/realtime mixing

## G06 State Machine
- no illegal transition
- READY cannot auto-enter

## G07 Portfolio
- broker positions reconcile
- stale portfolio blocks sizing

## G08 AI
- critical hallucination = 0 in golden
- unsupported numeric extraction rejected

## G09 Execution
- idempotency
- reject/cancel/partial fill
- duplicate submission prevention

## G10 Shadow
- >=20 trading days
- operator review complete

## G11 Operations
- alerts
- backups
- restore drill
- incident runbook

## G12 Rights / Terms
- source terms reviewed
- personal-use market-data plan verified
- no prohibited redistribution assumption

## Status

Only all pass:
`COMMERCIAL_V1_READY`

Otherwise：
`PRODUCTION_BLOCKED` + blockers。
