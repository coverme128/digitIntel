# MASTER CONTRACT — US Opportunity Engine Commercial V1.0

## 1. 正式名称

**US Opportunity Engine**

内部产品代号：`USOE`

版本：`Commercial V1.0`

## 2. 产品定位

US Opportunity Engine 是一个个人使用的美股事件驱动机会决策系统。

它不输出“应该买哪只股票”的黑箱结论，而是持续回答：

1. 哪家公司刚刚发生了足够重要的变化？
2. 这个变化是否真实、是否可量化、是否有官方证据？
3. 市场已经反应了多少？
4. 是否形成值得继续观察的 Opportunity？
5. 什么条件满足时可以进入 `READY`？
6. 什么条件破坏时 Opportunity 必须失效？
7. 当前个人组合是否允许继续承担该风险？
8. 实际执行以后，该机会是否按原 thesis 演化？

## 3. Commercial V1 目标

V1 必须形成完整闭环：

`DISCOVER → VERIFY → NORMALIZE → CALCULATE → QUALIFY → WATCH → READY → ENTERED → MANAGE → EXITED/INVALIDATED`

并做到：
- 用户每天无需浏览大量资讯；
- 系统允许“今天 0 个机会”；
- AI 不能直接产生事实或交易结论；
- 所有重要数字可复算；
- 所有 Opportunity 有 evidence lineage；
- 所有状态变化可审计；
- 交易执行必须显式由用户批准；
- 任何数据源失败不得静默降级为虚构结果。

## 4. 四层职责

### 01-product
定义：
- 用户是谁
- 用户看到什么
- 用户如何行动
- 信息层级
- 用户状态
- 页面与交互
- 产品边界

### 02-domain-rules
定义：
- Event 类型
- Materiality
- Fundamental Change
- Price Reaction
- Historical Analog
- Opportunity Qualification
- Portfolio Risk
- Invalidation
- Evidence / confidence
- Domain rule versioning

### 03-implementation
定义：
- 系统架构
- Source adapters
- 数据模型
- Pipelines
- API
- AI contract
- Observability
- Security
- Testing

### 04-production-handoff
定义：
- Codex 实施顺序
- 环境和部署
- 数据初始化
- 发布门禁
- 运营手册
- 验收清单
- 回滚机制

## 5. 优先级

发生冲突时：

`MASTER > Domain Rules > Product > Implementation > Production Runbook`

说明：
- MASTER 决定产品边界。
- Domain 决定“算什么”和“怎么算”。
- Product 不得改变 Domain 数学含义。
- Implementation 不得为了实现方便修改业务定义。
- UI 不得把 WATCH 显示成 BUY。

## 6. Frozen Items

Commercial V1 冻结以下内容：

1. Primary truth source = SEC EDGAR。
2. Market data primary = Massive。
3. Broker/portfolio primary = IBKR。
4. Company IR = official supplemental fallback，不做全市场爬虫入口。
5. V1 Universe 默认：
   - S&P 500
   - Nasdaq 100
   - User Watchlist
   - 去重后统一 Security Registry
6. V1 Opportunity Families：
   - Earnings / Guidance
   - Capital Return / Buyback
   - Insider Open-Market Buy
   - Activist / Beneficial Ownership
   - Material Corporate Event
   - Financing / Dilution
   - M&A / Special Situation（仅基础事件识别和观察，不做复杂 merger-arb 概率模型）
7. User action states：
   - IGNORE
   - WATCH
   - READY
   - ENTERED
   - MANAGE
   - EXITED
   - INVALIDATED
8. AI 只能：
   - 分类
   - 抽取
   - 比较
   - 解释
   - 总结
   不得生成不可证实事实、价格预测、自动下单指令。
9. 自动交易关闭。
10. Options / social / news aggregation / alternative data 不进入 V1 核心。

## 7. Mutable Items

允许以后通过 Correction Pack 修改：
- Event thresholds
- Opportunity thresholds
- Universe 扩展
- UI 文案
- Historical analog window
- Sector ETF mapping
- Notification thresholds
- AI provider/model
- Cache and queue configuration

但任何修改必须：
- 增加 rule_version
- 不覆盖历史计算结果
- 可对旧机会重放
- 记录 migration note

## 8. Codex 实施顺序

必须按以下顺序：

1. Canonical data model
2. Security registry
3. SEC ingestion + evidence storage
4. Massive historical/realtime adapter
5. Event normalization
6. Fundamental delta engine
7. Price reaction engine
8. Opportunity state engine
9. Portfolio / IBKR read-only integration
10. UI
11. User-approved execution workflow
12. Observability + replay
13. Backtest / shadow mode
14. Production gates
15. 才允许真实资金连接

禁止先做漂亮 Dashboard 再补规则。

## 9. Correction Pack 规则

格式：

`us-opportunity-engine-correction-v1.0.x/`

必须包含：
- CHANGELOG
- AFFECTED-CONTRACTS
- SCHEMA-MIGRATION（如有）
- RULE-MIGRATION（如有）
- TEST-DELTA
- ROLLBACK

禁止直接覆盖 V1 规则文件。

## 10. Commercial Launch Gate

正式标记 `COMMERCIAL_V1_READY` 必须同时满足：

- SEC ingest 连续 14 个交易日稳定
- market data 无不可解释缺口
- evidence lineage 100% 可追溯
- 关键数值 reconciliation 通过
- AI factual hallucination gate = 0 critical
- opportunity replay 可复现
- shadow mode 至少 20 个交易日
- 所有 ENTER 都由用户显式确认
- portfolio position reconciliation 通过
- execution sandbox/paper trading 通过
- production monitoring / alert / rollback 完整
- 法务免责声明与数据许可核验完成

否则只能处于：
- `ENGINEERING_READY`
- `SHADOW_READY`
- `PAPER_TRADING_READY`
- `PRODUCTION_BLOCKED`
之一。
