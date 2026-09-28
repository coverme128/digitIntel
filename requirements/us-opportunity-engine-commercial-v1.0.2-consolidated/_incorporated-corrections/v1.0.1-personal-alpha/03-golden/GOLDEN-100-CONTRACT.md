# Golden 100 Contract

## Purpose

Golden 100 不是为了证明策略一定赚钱。

它有三个目的：

1. 验证 event/fact/rule 计算正确
2. 检查规则是否明显产生低质量候选
3. 建立初始 historical outcome baseline

## Distribution

- 30 Earnings / Guidance
- 15 Buyback
- 15 Insider Open-Market Buy
- 10 Activist / 13D
- 10 Financing / Dilution
- 10 Material Corporate Event
- 10 M&A / Special Context

## Each Fixture Must Contain

- security
- CIK
- accession
- form
- accepted_at
- official evidence URL
- raw source hash
- event family/type
- normalized facts
- expected materiality
- initial price reaction
- sector-adjusted reaction
- expected role:
  - ENTRY_CANDIDATE
  - POSITION_RISK
  - CONTEXT_ONLY
- expected state range
- 1D/5D/10D/20D outcomes
- MFE
- MAE
- notes

## No Look-ahead

All expected pre-entry calculations must use only data available at that historical timestamp.
