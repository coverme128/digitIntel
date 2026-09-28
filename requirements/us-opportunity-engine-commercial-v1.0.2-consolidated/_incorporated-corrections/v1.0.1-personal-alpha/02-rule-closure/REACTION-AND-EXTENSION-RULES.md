# Reaction & Extension Rules

## Principle

Good news + large gap ≠ good entry.

## Baseline Extension Filter

For positive event candidates:

Sector-adjusted initial reaction:
- <= +8%: normal candidate zone
- +8% to +15%: CAUTION
- > +15%: EXTENDED

Override EXTENDED only if:
- family-specific historical analogs support continuation
- sample n >= 30
- median 5D excess return positive
- median MAE acceptable under configured risk budget

## Adverse Reaction

Positive fundamental event + negative price reaction:
- never auto-label underreaction
- classify `ADVERSE_REACTION`
- require additional review

## Gap Chase Prevention

READY cannot trigger:
- within first 5 minutes after regular open for gap events
- on stale quote
- if bid/ask spread exceeds configured liquidity threshold
