# US Opportunity Engine Commercial V1.0.2 — Consolidated Release

合并：
- Commercial V1.0
- Personal Alpha Rule & Golden Closure v1.0.1
- AI Independence & Decision Export Correction v1.0.2

## 当前正式产品定义

**Deterministic Personal Alpha Engine + Optional AI Analysis Layer**

## Core invariants

- AI OFF 可完整运行
- AI ASSIST 不改变核心结果
- Opportunity / WATCH / READY / Entry / Invalidation / Portfolio Risk / Outcome 均来自 deterministic core
- Decision & Analysis Export 是核心能力，不是 AI 功能
- JSON / Markdown / CSV 导出在 AI OFF 下必须可用
- 导出可交给 ChatGPT、WorkBuddy、Claude 等外部 AI
- AI 不得直接修改交易状态机或触发订单

## Implementation order

1. Commercial V1 foundation
2. v1.0.1 Personal Alpha rule closure
3. v1.0.2 AI independence + export
4. Golden replay
5. Shadow
6. Paper
7. Small-capital live validation
