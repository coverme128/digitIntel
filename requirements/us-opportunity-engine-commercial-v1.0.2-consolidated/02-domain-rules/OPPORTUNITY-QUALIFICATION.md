# Opportunity Qualification

## Qualification Gates

必须全部通过：

### G1 Evidence
官方证据存在且可打开。

### G2 Freshness
事件在允许时间窗口内。

### G3 Materiality
达到该 event family 的 materiality rule。

### G4 Data Quality
关键字段完整，单位/期间一致。

### G5 Reaction
市场数据窗口完整。

### G6 Opportunity Pattern
满足具体 family pattern。

### G7 Risk
没有 hard block。

## Output

系统不输出单一“Alpha Score”作为最终结论。

输出：
- state
- reason_codes[]
- materiality_bucket
- reaction_bucket
- data_quality
- evidence_quality
- trigger_status
- invalidation_status
- risk_flags[]

## Why No Total Score

总分会掩盖：
- 高 materiality 但数据缺失
- 好事件但股价已经过度反应
- 好机会但组合暴露过高

因此 Commercial V1 以 gate + reason codes 为主。
