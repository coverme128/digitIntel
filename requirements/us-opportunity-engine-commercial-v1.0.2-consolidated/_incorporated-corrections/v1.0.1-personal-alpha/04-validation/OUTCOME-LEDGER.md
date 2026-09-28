# Outcome Ledger

Every ENTERED opportunity must produce one immutable outcome record.

## Required

- trade_id
- opportunity_id
- rule_version
- account_snapshot_id
- entry_intent
- actual fills
- planned loss
- actual max adverse excursion
- max favorable excursion
- exit reason
- realized pnl
- fees
- slippage
- net pnl

## Derived

- R multiple
- holding period
- benchmark excess return
- family expectancy contribution

## Why

The system cannot learn whether it helps the user make money without an outcome ledger.
