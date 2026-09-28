# 个人研究版与 DeepSeek

本次重点是无券商账户的个人研究：注册关注股票 → 更新 SEC → 补齐 EX-99 → 候选提取 → 原文核对 → 研究列表 → Massive 行情更新。真实案例与长期验收按用户要求后置，不把合成测试当成真实效果证明。

## 使用

1. 演示入口 `http://127.0.0.1:8787/#research` 可查看“每日研究”。该库仍是隔离合成数据。
2. 真实个人工作区：`.venv/bin/python -m usoe --port 8788`，访问 `http://127.0.0.1:8788/#research`。不会要求配置 IBKR。
3. 在设置页注册股票、CIK、公司名和板块。在每日研究页勾选需要关注的股票及事件类型；默认财报/指引优先。取消股票勾选会暂停本研究流程对该股票的 SEC 更新（不删除历史证据，也不影响另行启动的独立任务）。
4. 配置本机 `.env` 后重启服务：

```dotenv
SEC_USER_AGENT=USOpportunityEngine/1.0 contact your-email@example.com
MASSIVE_API_KEY=
MASSIVE_DATA_MODE=historical
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_DAILY_REQUEST_LIMIT=20
```

已有 SEC 联系配置保留，不需重复提供。网页不读取或回显 Key。模型名可以修改；默认值依据本次查阅的 DeepSeek 官方文档。

5. 点“更新研究数据”，或先在设置页同步 SEC。证据中心可以“补齐 EX-99 展品”，再点“DeepSeek 提取候选事实”。支持匹配 EX-99/earnings/press release 文件名的 HTML/文本，每次最多 5 份；PDF、未匹配附件需人工补充，未宣称覆盖全部披露。
6. 在设置页切换 AI Assist。仅有 Key 不会自动发送数据；手动点击提取/解释或在研究偏好中启用自动提取才会调用。
7. 每日研究页打开候选草稿，查看原文并修改 JSON。确认指标含义、单位、期间、GAAP 口径和数值后勾选复核，再“验证并纳入研究”。数字与原文不一致、引用不存在、公司/时点不匹配、未知指标、重复指标均阻断。
8. 新研究记录的行情初始明确为待补齐。进入详情点击“同步 Massive 并重新计算”；配置行情 Key 后，研究轮询也会更新。没有行情不会生成虚构价格或声称研究条件满足。

## 状态独立

“研究条件满足”只表示证据、基本面、价格和失效规则等非账户条件通过，不是 READY 交易状态。无账户只影响执行，不影响研究列表；原有仓位风控、订单确认和规则重放保留不变。

研究视图会按当前时间重新检查新鲜度。历史/延迟数据不能冒充实时研究价格条件；未满足的条件直接列出。查看页面不触发 AI 或外部网络请求。

## DeepSeek 边界

- 直接调用官方 HTTPS `/chat/completions`，JSON object 输出，不依赖外部 SDK。
- 提取只发送本机已归档的 SEC 公开披露、已归档展品及最多一份此前财报/8-K相关披露。单文档最多 40,000 字符，总计最多 160,000 字符，明确标记截断；不是全长文本覆盖保证。
- 财报提取当前支持注册的数值型指标、指引范围及财报数据；自由文本语义与期间分类由用户复核。不自动处理所有公司特有指标或全部事件族。
- 解释只发送选定研究事实、计算和行情摘要，不发送持仓、账户余额、订单或凭证。合成数据带 `is_demo` 标识。
- 原文按不可信数据处理，模型不能使用工具、访问文中链接或改变账户状态。模型输出单独存储，不把其自称“已核实”视为证据。
- 同一模型/任务/输入哈希复用缓存；默认每日最多 20 次请求，失败尝试也计数，无隐式付费重试。
- AI 关闭、缺 Key、超时、格式错误、输出截断均明确降级；既有事实和核心计算不变。人工导入与确定性研究在 AI Off 下可用。
- 原始 AI 产物在 `ai_artifacts` 不可变保存；人工修订稿在 `research_drafts`；批准后使用既有证据/事实验证入口，记录审计。

## 持续更新与提醒

```bash
.venv/bin/python -m usoe --port 8788 --poll-research 900
```

最小间隔 300 秒。该模式包含 SEC 更新，不与 `--poll-sec` 同时启动。自动 DeepSeek 提取还要求 AI Assist、有效 Key 及“自动提取”偏好全部开启，每轮最多 5 份；不会自动批准事实或下单。关闭服务/电脑休眠后轮询停止，当前不安装开机启动服务。

候选待复核、研究条件满足和更新失败以去重的本机研究提醒保存，可标记已读。未发送邮件、短信或桌面推送。个人关注变更不影响用户另行配置的独立数据同步进程。

## 新增 API

沿用本机会话、同源 Origin、CSRF 和 JSON 要求。

| API（`/api/v1` 前缀） | 用途 |
|---|---|
| GET `/research` | 研究视图、候选、偏好、提醒及上次运行 |
| POST `/research/preferences` | `families,watchlist_only,auto_extract,security_ids?`；null=全部有效注册证券，[]=不更新任何证券 |
| POST `/research/run` | 单次研究更新，不执行交易 |
| POST `/research/exhibits` | `filing_id`；补齐支持的 SEC 展品 |
| POST `/research/extract` | `filing_id`；DeepSeek 候选提取，不写入 canonical facts |
| POST `/research/drafts/{id}/approve` | `confirmed:true,candidate?`；人工复核后严格验证并纳入研究 |
| POST `/research/notices/read` | `id`；标记提醒已读 |
| GET `/ai/status` | 配置存在性/模型/最近请求状态，不返回 Key |
| POST `/opportunities/{id}/explain` | 单机会辅助解释，独立于核心输出 |

## 验证范围

本次只使用合成披露和模拟 DeepSeek/SEC 响应进行测试。没有以用户账号请求模型或抓取真实案例。真实提取质量、完整真实行情链路、长期提醒有效性后续再验收。

接口参考：[DeepSeek 官方调用说明](https://api-docs.deepseek.com/guides/harness)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。
