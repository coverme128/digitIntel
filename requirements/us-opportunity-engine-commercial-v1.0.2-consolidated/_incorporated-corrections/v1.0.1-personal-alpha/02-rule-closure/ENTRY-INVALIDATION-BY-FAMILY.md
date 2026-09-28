# Entry & Invalidation by Family

## Common Preconditions

READY requires:
- state = WATCH
- evidence complete
- market data fresh
- no hard portfolio block
- security tradable
- no active contradiction
- minimum risk/reward worksheet available

## 1. Earnings / Guidance

READY when:
- event HIGH/VERY_HIGH
- price holds above event-session VWAP or reclaims it
- not EXTENDED by current reaction filter
- relative volume >=1.25x
- sector relative strength not materially negative
- no new contradicting filing

Invalidation:
- close below pre-event close after confirmation
- material guidance reversal
- thesis-breaking filing
- 10 trading days without confirmation = time invalidation by default

## 2. Buyback

READY when:
- buyback >=5% market cap
- balance-sheet capacity pass
- price not >10% above pre-event close unless historical rule supports
- either:
  - event-day hold + subsequent high breakout
  - orderly pullback and reclaim of event VWAP

Invalidation:
- financing/dilution offsets buyback
- liquidity deterioration
- price closes below pre-event low
- no confirmation within 15 trading days

## 3. Insider Cluster

READY when:
- cluster rule pass
- stock not in obvious post-news vertical extension
- base/reclaim pattern after final qualifying Form 4
- no material adverse filing

Invalidation:
- new adverse fundamental event
- price closes below cluster-window low
- 20 trading days without confirmation

## 4. Activist 13D

READY when:
- active Item 4 intent
- position size meaningful
- initial reaction not EXTENDED
- either continuation after consolidation or pullback/reclaim pattern

Invalidation:
- filer reduces/withdraws active intent
- amended filing weakens thesis
- price closes below pre-13D reference low
- 20 trading days without confirmation

## 5. Material Corporate Event

No generic READY rule.

Every subtype must bind to subtype-specific rule.
Unknown subtype remains WATCH/REVIEW_REQUIRED.

## 6. Portfolio Overlay

Even if market READY:
- portfolio HARD BLOCK => `READY_BLOCKED`
- portfolio WARNING => keep READY with warning
- only user confirmation can ENTER
