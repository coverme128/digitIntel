# AI Independence Contract

## Product invariant

`CoreOutput = f(CanonicalData, RuleVersion, MarketSnapshot, PortfolioSnapshot)`

不得依赖 LLM output。

## AI_MODE=OFF

必须完整支持：
- Event ingestion
- Canonical facts
- Fundamental change
- Price reaction
- Historical analog
- Opportunity qualification
- WATCH / READY / INVALIDATED
- Entry / invalidation
- Portfolio risk
- Position sizing worksheet
- Outcome ledger
- Decision & Analysis Export

## AI_MODE=ASSIST

在 OFF 全部能力之上增加：
- 非结构化 filing / IR 辅助提取
- 文本比较
- 解释
- 摘要
- Research notes

## Core parity

允许变化：
- `ai_explanation`
- `ai_summary`
- `ai_notes`

禁止变化：
- facts
- calculations
- opportunity state
- triggers
- invalidation
- portfolio risk
- sizing
- order eligibility

## AI failure

AI timeout / unavailable / quota / malformed output：
- 不阻断 deterministic core
- 标记 `AI_ASSIST_UNAVAILABLE`
- 用户仍可查看、导出和执行核心工作流

## Candidate extraction

AI 抽取结果只能进入 `CandidateExtraction`。
只有通过 deterministic validation 后才能成为 Canonical Fact。

## Provider independence

核心不得绑定任何单一 AI provider。
