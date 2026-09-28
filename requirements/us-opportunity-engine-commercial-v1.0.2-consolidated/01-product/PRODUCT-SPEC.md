# Product Spec

## 1. Target User

Commercial V1 只服务一个主要 persona：

**有美股交易经验、自己管理账户、愿意等待事件型机会的个人投资者。**

不是：
- 高频交易员
- 完全新手
- 需要投顾代客决策的人
- 需要机构多席位协作的人

## 2. 核心价值

把“美股每天的大量信息”压缩为：

- 0–3 个高价值新机会
- 少量待确认 Watch
- 已持仓需要关注的 thesis change
- 明确的 invalidation

用户不是来读资讯，而是来减少低质量交易。

## 3. 用户每天的标准动作

### Pre-market
- 打开 Today
- 查看 New Opportunities
- 对每个候选执行：Ignore / Watch
- 对 READY 检查 entry condition

### Market hours
- 只接收：
  - READY trigger
  - Position risk alert
  - Invalidation
- 不鼓励持续刷盘

### Post-market
- 查看：
  - 新 filing
  - Earnings events
  - Position thesis updates
  - 当日执行和结果

## 4. 核心页面

### Today
显示：
- New Opportunities
- Ready
- Position Attention
- Invalidated
- Filtered Event Count

### Opportunity Detail
必须展示：
- Catalyst
- What Changed
- Evidence
- Magnitude
- Price Reaction
- Sector Context
- Historical Analog
- Risks
- Entry Conditions
- Invalidation
- Holding Window
- Rule Version

### Watchlist
按状态：
- WATCH
- READY
- INVALIDATED

### Portfolio
显示：
- Position
- Original Thesis
- Current Thesis State
- Exposure
- Concentration
- New Events
- Exit / Reduce triggers

### Evidence
可查看：
- filing
- filing section
- exhibit
- normalized facts
- calculated deltas
- source timestamp

## 5. 产品原则

- 允许没有机会。
- 不用一个总分代替事实。
- 不把 AI 文本作为证据。
- 不把价格上涨等同机会。
- 不把一次 insider sale 视为 bearish。
- 不把 daily short volume 当 short interest。
- 不使用“强烈买入”等投顾式文案。
- 所有 Action 都是 workflow state，不是收益承诺。
