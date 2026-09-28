# Codex Closure Instructions

Apply this package after Commercial V1.0.

## Do Not Redesign

Do not:
- add modules
- change navigation
- add options/social/news
- change sources
- replace state machine

## Implement

1. Add event role:
   - ENTRY_CANDIDATE
   - POSITION_RISK
   - CONTEXT_ONLY

2. Add exact baseline thresholds.

3. Add family-specific READY/invalidation evaluators.

4. Add portfolio risk defaults.

5. Add Outcome Ledger.

6. Add Personal Edge analytics.

7. Add Golden fixture framework.

8. Add validation ladder states.

## Migration

Existing opportunities:
- recompute role
- retain old state history
- if old READY violates new role, transition with migration reason
- never erase prior state

## New Gates

- ROLE_MATRIX_READY
- EXACT_RULES_READY
- OUTCOME_LEDGER_READY
- GOLDEN_REPLAY_READY
- PERSONAL_ALPHA_BASELINE_READY

## Final

After implementation do not claim `TRADING_PROVEN`.

Allowed:
`PERSONAL_ALPHA_VALIDATION_READY`

Then enter Shadow/Paper/Small Capital Live.
