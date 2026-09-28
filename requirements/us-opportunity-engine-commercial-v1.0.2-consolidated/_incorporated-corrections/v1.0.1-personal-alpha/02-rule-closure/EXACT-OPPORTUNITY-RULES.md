# Exact Opportunity Rules — Baseline v1.0.1

这些是 Commercial V1 的初始 deterministic baseline。
它们必须先通过 Golden / Shadow / Paper 验证，不能被描述为“已证明 profitable”。

## 1. Earnings / Guidance

### Materiality

Revenue guidance midpoint change:
- < 3%: LOW
- 3%–5%: MEDIUM
- 5%–10%: HIGH
- > 10%: VERY_HIGH

EPS guidance midpoint change:
- < 5%: LOW
- 5%–10%: MEDIUM
- 10%–20%: HIGH
- > 20%: VERY_HIGH

Gross margin guidance:
- < 50 bps: LOW
- 50–100 bps: MEDIUM
- 100–200 bps: HIGH
- > 200 bps: VERY_HIGH

Structural overrides:
- guidance withdrawal = MATERIAL_RISK
- first-time positive FCF guidance = HIGH
- sign reversal from decline to growth = HIGH when evidence complete

### WATCH Gate

至少满足：
- one HIGH material change, or
- two MEDIUM material changes
- evidence E1/E2
- market reaction window complete
- no contradictory filing

### Reaction Filter

Initial excess return vs sector:
- > +15%: EXTENDED by default
- +8% to +15%: needs stronger follow-through rule
- -5% to +8%: normal candidate zone
- < -5% despite positive fundamental change: ADVERSE; do not auto-classify underreaction

## 2. Buyback

Authorization / market cap:
- < 2%: LOW
- 2%–5%: MEDIUM
- 5%–10%: HIGH
- > 10%: VERY_HIGH

WATCH requires:
- >=5%, or
- >=2% with strong prior execution credibility and balance-sheet support

Hard downgrade:
- material net leverage stress
- simultaneous large dilution
- authorization without execution history when cash capacity weak

## 3. Insider Open-Market Buy

Single insider:
- purchase < $100k: usually context only
- $100k–$500k: MEDIUM
- > $500k: HIGH

Cluster definition:
- >=2 qualifying insiders within 10 calendar days

Cluster HIGH when:
- aggregate >= $500k
- includes CEO/CFO/Chair OR >=3 directors
- transaction code confirms open-market purchase

Exclude:
- grant
- option exercise
- gift
- tax withholding
- transfer

## 4. Activist / 13D

WATCH when:
- initial 13D ownership >=5%
- Item 4 indicates active intent
- no purely passive interpretation
- filing evidence complete

HIGH when:
- governance change
- board representation
- strategic alternatives
- capital allocation demand
- sale process advocacy
is explicitly present

## 5. Material Corporate Event

V1 whitelist:
- material contract/agreement
- asset sale
- major restructuring
- debt refinancing with material liquidity impact
- CEO/CFO change
- material impairment
- large customer disclosure

Must be mapped to a concrete economic mechanism.
Free-text “important news” is not sufficient.

## 6. Financing / Dilution

Default role = POSITION_RISK.

Potential dilution:
- <3%: LOW
- 3%–7%: MEDIUM
- 7%–15%: HIGH
- >15%: VERY_HIGH

Do not create long-entry READY solely from financing event.
