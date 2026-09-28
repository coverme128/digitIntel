# Golden Acceptance

## Parser / Fact

- critical fact accuracy: 100%
- evidence linkage: 100%
- ticker/CIK mapping: 100%
- timestamp/session mapping: 100%

## Rule

- no illegal state transition
- POSITION_RISK event cannot become READY via generic path
- CONTEXT_ONLY event cannot become READY
- EXTENDED reaction cannot become READY without explicit override evidence

## Statistical Interpretation

Golden 100 is not large enough to declare profitability.

Allowed conclusions:
- implementation correct / incorrect
- rule obviously defective / not obviously defective
- family warrants shadow testing

Not allowed:
- “策略已证明赚钱”
- “胜率稳定”
- “可以直接上大资金”
