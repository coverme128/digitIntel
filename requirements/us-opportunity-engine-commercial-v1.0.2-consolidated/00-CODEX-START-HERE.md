# CODEX — START HERE

你正在实施 `US Opportunity Engine Commercial V1.0`。

这不是 Demo、原型、静态页面或 PRD 转 UI 任务。必须按正式可运行产品实现。

## 必读顺序

1. `MASTER-CONTRACT.md`
2. `02-domain-rules/*`
3. `03-implementation/DATA-MODEL.md`
4. `03-implementation/ARCHITECTURE.md`
5. `03-implementation/PIPELINES.md`
6. `01-product/*`
7. `04-production-handoff/*`

## 第一次回复必须先做

不要立刻编码。先返回：

### A. Contract Understanding
说明：
- 产品主链
- V1 边界
- Frozen Items
- AI 边界
- Execution 边界

### B. Repository Assessment
如果在现有仓库：
- 当前架构
- 可复用模块
- 冲突
- migration 需求

### C. Implementation Map
按 Phase 0–10 映射：
- 要改的目录
- 新模块
- DB migration
- source adapter
- test fixture
- release gate

### D. Blockers
只列真实 blocker。
不得把“尚未实现”本身写成需求不清。

## 强制约束

- 不得自行修改 Domain semantics。
- 不得将 WATCH/READY 显示成 BUY/STRONG BUY。
- 不得加入未要求的 Options、social、news feed。
- 不得使用 AI 直接写 canonical facts。
- 不得让 AI 触发订单。
- 不得跳过 raw source retention。
- 不得在数据缺失时用 mock 结果替代生产结果。
- mock/fixture 只允许在 test 环境。
- 所有真实 source failure 必须显式显示。
- Commercial V1 必须支持“0 Opportunity”。

## 实现策略

优先建立：
`Raw → Canonical → Derived → Presentation`

禁止：
`AI response → UI card` 直接成为主链。

## 每个 Phase 完成后的反馈格式

- Implemented
- Tests
- Real data proof
- Remaining blockers
- Gate status
- Changed files
- Migration notes

## 最终状态

只有 `RELEASE-GATES.md` 全部通过后才能标记：

`COMMERCIAL_V1_READY`

否则必须使用更准确的状态并列出 blocker。
