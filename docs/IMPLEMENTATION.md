# v1.0.2 实现覆盖与发布门禁

## 交付定义

当前是单用户、本地、可运行的工程实现。`PRODUCTION_BLOCKED` 是实际状态，不是假定全部验收已通过。需求中的运行时间门禁、账户授权、真实数据历史验收不能用合成数据替代。

| 需求域 | 已实现 | 当前限制 / 下一发布门禁 |
|---|---|---|
| Canonical model | 证券、来源、原文、披露、证据、事实、事件、市场/组合快照、计算、机会、转换、订单草稿、持仓、Thesis、结果和审计 | SQLite 单用户实现；生产 PostgreSQL / 对象存储 / 权限迁移未执行 |
| Universe | CIK / ticker 冲突拦截，SEC 再校验；按日期生效的 SP500 / NASDAQ100 / USER_WATCHLIST 成员导入 | 不捏造当前或历史指数名单；需合法来源的成分数据 |
| SEC | 合规 UA、请求节流、退避重试、submissions、primary document、companyfacts、accession 去重、accepted timestamp、不可变原文；可选轮询与持久任务记录 | 默认最近 5 份、最多 20 份，不是全历史补齐；独立展品索引抓取、全表单自动解析尚未完成。无法确定的事件进入 REVIEW_REQUIRED |
| Canonical ingestion | 证据归属 / 时点、数值 token 与比例、单位注册、期间、fact version 校验；历史证据可与当前披露比较 | 非结构化语义需要用户复核；AI 候选不得直接晋升 canonical |
| Massive | 已认证历史分钟 OHLCV 获取与原文保存；时间戳排序与空窗口检查，模式显式标记 | 未实现 WebSocket、完整分页补齐、企业行动调整、自动基准/板块对齐与实时行情持续校验。历史窗口不会假装完整实时窗口 |
| Fundamental | 指引中值变化、利润率 bps、FCF、回购/市值、摊薄比例、交易价差、内部人集群 | 公司特有指标、完整 YoY/QoQ 加速度、跨报表复核仍需扩展注册与解析 |
| Reaction | 原始 / SPY / 板块超额反应、量比、VWAP、gap、range；extended/adverse/caution；陈旧和延迟数据限制 | 完整交易所日历由输入提供，覆盖缺失时阻止 READY；不会用简单工作日冒充交易日 |
| Family rules | v1.0.1 materiality 分层、候选/风险/背景角色、各家族的入场条件与默认等待期限 | 8–15% 需要额外确认、EXTENDED override 和未知 corporate subtype 缺乏具体公式，保守阻止 READY；不擅自配置收益优化阈值 |
| State machine | 合法边检查、显式用户入场、失效、忽略、持仓管理、退出；终态不自动复活 | 跨新披露自动关联已有 Thesis 的完整语义判别未实现；可用新版本事件和快照重新计算 |
| Portfolio | 风险/集中度/现金/开放风险 sizing；陈旧、未知购买力、对账失败硬阻断；相关性/事件聚集警告输入 | IBKR 只读原始快照进入复核队列，完整 conid/security 自动对账与正式 paper broker 未验收 |
| Execution | 隔离演示库里的草稿、二次确认、幂等、串行事务防重复、确认前重校验、取消、Thesis / 成交 / 退出记录 | 本地单次全成交模拟，不是券商 paper trading；部分成交、券商拒单、券商取消/成交对账、生产重新认证未实现。真实订单始终禁用 |
| Outcome / learning | 不可变 entry/exit、净损益、费用、R 倍数、持有天数、family review 样本阈值 | 无价格路径时 MFE / MAE / 滑点 / 基准收益为 null，明确显示未采集；完整历史路径分析和家庭策略禁用工作流未验收 |
| Historical analog | 家族匹配、禁止未来 outcome、样本不足提示、描述统计 | 高级公司/板块/趋势/估值匹配未完成；没有内置真实类比样本 |
| AI independence | 纯函数核心不发出 AI 请求；AI fields 从输入核心哈希剔除；OFF/ASSIST 导出一致 | AI adapter UI 降级标记已实现，外部解释服务 / candidate extraction 持久管道未接入 |
| Export | 单机会、today、watchlist、portfolio、events、outcomes、performance 的 JSON/Markdown/CSV；核心哈希与快照元信息，CSV 注入转义 | 导出仅本机授权会话可读；二次分发需先检查数据授权 |
| UI | 中文、响应式、筛选、证据原文、条件进度、入场/退出确认、错误提示、空状态、审计、源状态 | 无新闻流、总分排名、收益预测或 AI 聊天首页 |
| Security / operations | 仅 loopback；Host 校验、SameSite HttpOnly 会话、同源 CSRF、CSP、密钥环境变量、审计链、指标、备份/校验/重放脚本 | 多用户认证、账户重认证、外部告警、自动备份策略、恢复演练、许可证核验尚未生产验收 |
| Validation | 单元/契约/HTTP 回归、100 合成家族场景、浏览器纸面闭环 | 真实 Golden 100、连续 14 日 SEC、20 日 Shadow、真正 IBKR paper gates 均未完成 |

## 冲突与保守解释

1. 原始 schema 的 materiality enum 未包含 `VERY_HIGH`；以合并补丁的精确分层为准，同时支持 `MATERIAL_RISK`。
2. 原始反应区间将 -5% 至 +8% 视为常规区间，但较后的 reaction correction 指定正面事件负价格反应需复核。本实现对负板块超额反应标记 ADVERSE。
3. `READY_BLOCKED` 是 trigger_status，机会保持 WATCH，不扩张用户状态枚举。
4. 未给出可执行阈值的 subtype / 历史 override 不启用；当前支持的 buyback 采用已验证 capacity 布尔事实，真实导入必须用户复核且有原文定位。
5. 原始 `event.schema.json` 仅作为需求存档保留，不直接覆盖。实际 API 契约见 `docs/API.md`，指标注册见 `config/metric-registry.json`。
6. 0.50% 为默认 sizing budget、1.00% 为手工数量的硬上限；证券 15%、板块 40%、同催化 35%、总未平仓计划风险 5% 为硬限制。
7. 应用自身的确认流程是待实现产品的功能；附件中面向 Codex 的行动指令没有被当成用户的外部操作授权。

## 必须保持的生产阻断

以下全部有证据才能宣布 COMMERCIAL_V1_READY：

- 真实 Golden 100：30 earnings / 15 buyback / 15 insider / 10 activist / 10 financing / 10 corporate / 10 M&A；每个样本有官方原文与实际历史结果。
- SEC 连续至少 14 个交易日稳定，完整市场窗口和数字对账通过。
- 至少 20 个交易日 Shadow，记录漏报、误报及 hypothetical outcomes。
- IBKR paper 覆盖正常、拒单、取消、部分成交、重新对账与重复提交防护。
- 数据许可 / 法务核验、外部告警与备份恢复演练完成。
- 真实资金开关须由单独实现、复核和授权的版本引入；本仓库没有可提交真实订单的函数。
