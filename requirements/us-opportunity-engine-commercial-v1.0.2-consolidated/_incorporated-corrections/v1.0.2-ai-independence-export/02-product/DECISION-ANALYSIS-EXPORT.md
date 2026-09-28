# Decision & Analysis Export

## 目的

把已经由确定性引擎算好的结果导出给：
- ChatGPT
- WorkBuddy
- Claude
- 其他外部 AI / 分析工具

## 格式

### JSON
完整机器可读格式。

### Markdown
直接复制给外部 AI，必须包含：
- Security
- Opportunity State
- Catalyst
- Evidence
- Fundamental Changes
- Price Reaction
- Historical Context
- Entry Conditions
- Invalidation Conditions
- Portfolio Context
- Risk Flags
- Outcome History
- Rule Version

### CSV
用于批量：
- opportunities
- events
- trades
- outcomes
- family performance

## Scope

支持：
- single opportunity
- daily opportunity set
- watchlist
- portfolio
- historical outcomes
- family performance

## Provenance

每个 export 必须包含：
- exported_at
- rule_version
- source_snapshot
- market_snapshot
- portfolio_snapshot
- ai_mode
- core_output_hash

`ai_mode` 只记录 provenance，不影响 core result。
