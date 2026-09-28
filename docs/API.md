# 本地 API 与数据契约

Base: `http://127.0.0.1:8787/api/v1`（demo）或 `:8788/api/v1`（shadow）。错误响应 `{error, code}`，400 参数错误、401 缺会话、403 安全阻断、404 不存在、409 工作流冲突、502 数据源降级。

## 会话与写入

`GET /session` 创建或复用 HttpOnly / SameSite=Strict 的本地会话，返回 `csrf_token`。

读取 API 需发送会话 Cookie。写入还需：

- `Content-Type: application/json`
- `Origin: http://127.0.0.1:<实际端口>`
- `X-CSRF-Token: <token>`
- 订单和退出的 create/confirm 还需 `Idempotency-Key: <唯一请求 ID>`

相同幂等 key 与相同 payload 返回之前结果；相同 key 与不同 payload 报错。每个端口使用不同 cookie 名；同一端口的多个页面复用会话。

## 查询

| 方法 / 路径 | 返回 |
|---|---|
| GET `/status` | 环境、规则、数据源、门禁、AI 模式、审计完整性 |
| GET `/today` | watch / ready / position attention / invalidated / filtered count |
| GET `/opportunities?state=&family=&sector=&symbol=&q=` | 过滤后的完整 CoreOutput 列表 |
| GET `/opportunities/{id}` | 完整 CoreOutput、状态转换、结果引用 |
| GET `/opportunities/{id}/replay` | 原始持久输入重放的哈希比较 |
| GET `/portfolio` | 快照、暴露、持仓与风险事件 |
| GET `/history` | exited / invalidated / ignored、outcomes、family performance |
| GET `/events` | canonical event packets |
| GET `/securities` | 证券注册表 |
| GET `/review-queue` | 官方披露和 broker 快照待复核队列 |
| GET `/order-intents` | 草稿、取消与纸面成交记录 |
| GET `/outcomes` | 不可变入场 / 退出结果 |
| GET `/performance` | 事件族描述性结果与复核等级 |
| GET `/audit` | 哈希链验证与最近 200 条日志 |
| GET `/evidence/{raw_id}/raw` | 原始 bytes 以 text/plain 打开，绝不执行抓取网页脚本 |
| GET `/metrics`（根路径） | Prometheus 兼容本地指标，需会话 |

## 用户工作流

- POST `/opportunities/{id}/watch` `{}`：仅 WATCH/READY，记录用户保留观察。
- POST `/opportunities/{id}/ignore` `{}`：合法状态进入 IGNORED，保留历史。
- POST `/opportunities/{id}/refresh` `{market_snapshot?: object}`：保存新快照，按原规则重新评估；不覆盖旧计算。
- POST `/order-intents`：`{opportunity_id, quantity, entry, invalidation, management_hypothesis}`。仅 demo、READY、有效 worksheet 可创建。
- POST `/order-intents/{id}/confirm`：`{confirmed:true}`。独立显式确认，重新检查价格、失效线、数据时效、组合、数量；生成本地模拟 fill / Thesis。
- POST `/order-intents/{id}/cancel`：`{}`，仅 DRAFT。
- POST `/positions/{id}/exit-intent`：`{price, fees, reason}`。
- POST `/exit-intents/{id}/confirm`：`{confirmed:true}`，关闭本地模拟持仓并追加结果。
- POST `/settings`：`{ai_mode:"off"|"assist"}`，不重算 core，不迁移状态。

任何缺失确认、过期草稿、过大仓位、重复活动草稿或终态的再次成交均返回错误，不做 best-effort 下单。

## 真实数据源

- POST `/securities`：`{security:{security_id,ticker,cik,issuer_name,sector,exchange},universe?,valid_from?}`
- POST `/sources/sec/sync`：`{security_id,limit?:5}`；仅 shadow；官方身份再次校验。
- POST `/sources/massive/bars`：`{symbol,start:"YYYY-MM-DD",end:"YYYY-MM-DD"}`；已归档历史分钟数据，不声称 realtime / complete。
- POST `/sources/ibkr/sync`：`{}`；只读账户、持仓、摘要，脱敏账号后进入对账队列。

## Canonical 导入

POST `/import` 或 `python3 scripts/manage.py --db ... import packet.json`：

```json
{
  "event": {
    "opportunity_id": "opp-example",
    "event_id": "evt-example",
    "security": {"security_id":"sec-example","ticker":"MSFT","cik":"0000789019","issuer_name":"Microsoft Corporation","sector":"Technology"},
    "accession":"<真实已归档 accession>",
    "form":"8-K",
    "event_family":"GUIDANCE_CHANGE",
    "event_type":"guidance_raised",
    "event_at":"<与当前 filing accepted_at 一致的带时区时间>",
    "catalyst":"用户复核后的事件描述",
    "is_demo":false,
    "evidence":[{"evidence_id":"ev-example","raw_document_id":"<真实已归档 raw id>","locator":"Item 2.02 paragraph 3","excerpt":"<在原文中逐字可匹配的完整片段>"}],
    "facts":[{"fact_id":"fact-example","metric_id":"current_revenue_guidance_low","value":1080000000,"unit":"USD","period_start":"2026-01-01","period_end":"2026-12-31","fact_version":1,"evidence_id":"ev-example","source_token":"1,080","source_scale":1000000}],
    "historical_analogs":[]
  },
  "market_snapshot": {
    "snapshot_id":"market-example",
    "ticker":"MSFT",
    "captured_at":"<带时区时间>",
    "is_demo":false,
    "complete":false,
    "data_mode":"historical"
  }
}
```

上面是结构示意，不是可执行的真实数据包，不能用占位证据建立真实机会。缺少旧指引/完整价格窗口时保留为非 READY。

- 事实 metric 与 unit 必须匹配 `config/metric-registry.json`。
- 来源 token 必须逐字出现在已引用 excerpt，数值按显式 scale 换算后必须与 value 相等。支持 1 / 1e3 / 1e6 / 1e9。
- 真实 evidence 必须在归档 SEC filing 上，CIK/security 归属相同，accepted_at 不晚于事件；至少一条 evidence 来自该事件当前 accession。
- 布尔/文本语义事实需 `reviewed_by:"USER"` 并有 source token；不会自动接纳 AI 意见。
- 每个事件 `(filing, family, type)` 去重；修订用新 accession / event，并通过 parent_event_id / supersedes 保留关系。
- 演示导入只能进入 demo 数据库，facts 的 JSON pointer 和数值必须与合成 raw_content 对账。

完整市场输入示例见 `usoe/demo.py::market`。它定义数据结构而非真实数据源。正式使用需填入自身有权使用且已对账的 anchor / price / SPY / sector / volume / VWAP / calendar / captured_at / spread 等输入；不得以示例值代替。日历明确提供起止覆盖范围及每个交易日的 UTC open/close，覆盖不完整阻止 READY。

## 导出

`GET /opportunities/{id}/export?format=json|markdown|csv`

批量范围：`/today/export`、`/opportunities/export`、`/watchlist/export`、`/portfolio/export`、`/events/export`、`/outcomes/export`、`/performance/export`。

JSON envelope：`export_version, exported_at, ai_mode, rule_version, source_snapshot, market_snapshot, portfolio_snapshot, core_output_hash, payload`。

哈希算法为对去除 AI 字段后的 payload 做 key 排序、无多余空白、UTF-8 / 非 ASCII 不转义 JSON 序列化，然后 SHA-256。核心代码是 `usoe.util.canonical` 与 `usoe.exports.core_only`。导出时间和 ai_mode 属于 envelope，不参与核心哈希。


## 集成 v2 API

所有 POST 仍要求本机会话、同源 Origin、JSON 和 X-CSRF-Token。以下接口均不返回凭证；真实数据写入仅允许独立 shadow 工作区。

| 方法 / 路径（`/api/v1` 前缀） | 作用 / 请求 |
|---|---|
| GET `/integrations` | 配置存在性、依赖、stream 状态、最近离线自检 |
| POST `/integrations/self-test` | `{}`；无网络合成验收 |
| POST `/sources/massive/bars` | `symbol,start,end,timespan?`；全部分页、未复权历史 bars |
| POST `/market/calculate` | `security_id,event_at,as_of?,event_family?,cluster_start?`；自动行情窗口并存档，不创建未经证据核验的事件 |
| POST `/opportunities/{id}/market-sync` | `{}`；依据原始事件拉取行情、存档并重算机会 |
| POST `/market/outcomes` | `security_id,entry_at,entry_price,price_basis,as_of?,quantity?,exit_price?,fees?,planned_loss?,planned_entry?`；研究结果，计算口径见集成指南 |
| POST `/sources/ibkr/sync` | `{}`；持仓、summary、ledger、挂单、执行对账，更新组合并重算机会 |
| POST `/broker/keepalive` | `{}`；保持已有会话，不登录/抢占会话，不返回 session token |
| POST `/broker/contracts/search` | `symbol`；IBKR 候选 conid，不自动选第一个 |
| POST `/broker/contracts/map` | `security_id,conid`；远程核验 USD 股票后保存映射 |
| POST `/broker/position-plan` | `security_id,invalidation_price,event_family`；保存计划后使旧组合失效，要求重新同步 |
| GET `/broker/orders` | 独立券商纸面账本，区别于本地演示 order-intents |
| POST `/broker/orders` | `side:BUY,opportunity_id,quantity,limit_price` 或 `side:SELL,security_id,quantity,limit_price,reason`；必须 Idempotency-Key，返回 DRAFT |
| POST `/broker/orders/{id}/preview` | `confirmed:true`；纸面 what-if，返回 PREVIEWED 或 PREVIEW_FAILED |
| POST `/broker/orders/{id}/submit` | `confirmed:true`；再次检查风险并持久预留，返回接单/警告/未知结果 |
| POST `/broker/orders/{id}/reply` | `confirmed:true,reply_id`；显式接受当前显示的券商警告 |
| POST `/broker/orders/{id}/cancel` | `confirmed:true`；取消请求，不把响应当成取消成交确认 |
| POST `/broker/orders/{id}/abandon` | `confirmed:true`；只丢弃尚未提交的本地草稿 |

重试同一 create 请求使用同一 Idempotency-Key。submit/reply/cancel 对同一已预留状态不会重新发请求；UNKNOWN 必须对账，不能通过改 key 自动重下。DAY/LMT/整数股数限定；live 账户拒绝。接口实现不代表 paper 账户验收已通过。

## 个人研究 / DeepSeek API

新增 `/research`、偏好/更新/提取/复核/提醒和 `/ai/status`、机会解释接口，详见 [个人研究 API](PERSONAL-RESEARCH.md#新增-api)。这些接口不改变已有交易 READY 或核心导出哈希。
