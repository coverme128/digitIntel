# Opportunity Role Matrix

不是所有 Event 都允许进入买入候选。

## ENTRY_CANDIDATE

允许进入 WATCH/READY：
- EARNINGS_REVISION
- GUIDANCE_CHANGE
- CAPITAL_RETURN / BUYBACK
- INSIDER_OPEN_MARKET_BUY
- ACTIVIST_OWNERSHIP
- 部分 MATERIAL_CORPORATE_EVENT

## POSITION_RISK

默认只对现有仓位形成风险提示：
- FINANCING_DILUTION
- guidance withdrawal
- material adverse management change
- restatement
- going concern / bankruptcy
- certain debt events

只有未来规则明确允许时才可转为反向交易候选。

## CONTEXT_ONLY

V1 只做上下文，不直接产生 READY：
- M&A_SPECIAL
- routine 13G
- ordinary dividend
- routine management grant
- non-material filing changes

## 原则

`Event detected ≠ Opportunity`
`Opportunity qualified ≠ READY`
`READY ≠ ENTER`
