# US Opportunity Engine — AI Independence & Decision Export Correction v1.0.2

本包修正 Commercial V1.0 + Personal Alpha Closure v1.0.1。

正式产品定义：

**Deterministic Personal Alpha Engine + Optional AI Analysis Layer**

核心冻结：
- 支持 `AI_MODE=OFF`
- 支持 `AI_MODE=ASSIST`
- 相同输入、相同 rule version、相同 market/portfolio snapshot 下，两种模式的核心结果必须一致
- AI 只负责辅助提取、比较、解释、摘要与研究
- AI 不得改变 Opportunity / WATCH / READY / Entry / Invalidation / Portfolio Risk / Outcome
- 所有核心确定性结果必须支持 `Decision & Analysis Export`
- Export 可交给 ChatGPT、WorkBuddy、Claude 或其他外部 AI 继续分析
- 即使产品内 AI 完全关闭，核心产品价值和闭环必须完整
