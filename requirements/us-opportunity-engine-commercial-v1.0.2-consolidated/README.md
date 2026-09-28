# US Opportunity Engine — Commercial V1.0

这是一个面向个人投资者自用的美股事件驱动机会引擎，不是资讯聚合器、荐股机器人、自动炒股 Demo 或“AI 猜涨跌”产品。

核心产品链路：

`Official Filing/Event → Structured Facts → Fundamental Change → Price Reaction → Historical Context → Opportunity State → Portfolio Context → User Action`

V1 的目标不是每天制造交易，而是把数千只股票压缩成少量“有明确催化、有证据、有触发条件、有失效条件”的候选机会。

## 固定交付结构

- `MASTER-CONTRACT.md`
- `01-product/`
- `02-domain-rules/`
- `03-implementation/`
- `04-production-handoff/`
- `schemas/`
- `config/`

## Commercial V1 核心源

1. SEC EDGAR：Primary truth source
2. Massive：Primary market-data source
3. Interactive Brokers (IBKR)：Portfolio / account / execution source
4. Company Investor Relations：Official supplemental fallback

## V1 明确不做

- 社交媒体情绪
- 新闻聚合平台依赖
- Options / IV / Greeks
- 自动无监督交易
- 全市场“AI评分”
- 预测下一交易日涨跌
- 黑箱买卖建议
- 另类数据
- 多券商
- 商业多租户

## 交付原则

所有核心 Opportunity 必须具备：
- 原始证据
- 可复算事实
- 明确规则版本
- 触发条件
- 失效条件
- 时间窗口
- 风险上下文
- 可追溯执行结果

Codex 应按 `04-production-handoff/CODEX-IMPLEMENTATION-PLAN.md` 顺序实施。
