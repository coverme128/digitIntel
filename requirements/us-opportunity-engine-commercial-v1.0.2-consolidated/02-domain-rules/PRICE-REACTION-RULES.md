# Price Reaction Rules

## 1. Event Anchor

根据 SEC accepted timestamp 映射：

- pre-market filing → previous close + premarket + open reaction
- regular-session filing → pre-event bar + 30m + close
- after-hours filing → regular close + after-hours + next open

## 2. Required Measures

- raw return
- excess return vs SPY
- excess return vs sector ETF
- relative volume
- gap %
- event-day range
- VWAP relationship

## 3. Reaction Gap

Reaction Gap 不是：
`fundamental % change - stock % move`

因为两者不可直接线性比较。

V1 定义为分类变量：
- UNDER_REACTION_CANDIDATE
- BALANCED_REACTION
- EXTENDED_REACTION
- ADVERSE_REACTION

分类输入：
- event magnitude bucket
- historical analog reaction
- sector-adjusted return
- event-day volume
- pre-event trend
- valuation context if available

## 4. Entry Rules

READY 至少需要：
- Opportunity 已 WATCH
- required session data complete
- configured price/volume confirmation pass
- no active invalidation
- no stale data
- portfolio risk gate not blocked

具体 trigger 按 event family 配置，不允许一个 trigger 覆盖全部事件。
