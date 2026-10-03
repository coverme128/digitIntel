# v1.0.2 实现覆盖与发布门禁

## 交付定义

当前是单用户、本地、可运行的工程实现。`PRODUCTION_BLOCKED` 是实际状态，不是假定全部验收已通过。需求中的运行时间门禁、账户授权、真实数据历史验收不能用合成数据替代。

| 需求域 | 已实现 | 当前限制 / 下一发布门禁 |
|---|---|---|
| Canonical model | 证券、来源、原文、披露、证据、事实、事件、市场/组合快照、计算、机会、转换、订单草稿、持仓、Thesis、结果和审计 | SQLite 单用户实现；生产 PostgreSQL / 对象存储 / 权限迁移未执行 |
| Universe | CIK / ticker 冲突拦截，SEC 再校验；按日期生效的 SP500 / NASDAQ100 / USER_WATCHLIST 成员导入 | 不捏造当前或历史指数名单；需合法来源的成分数据 |
| SEC | 合规 UA、请求节流、退避重试、submissions、primary document、companyfacts、accession 去重、accepted timestamp、不可变原文；可选轮询与持久任务记录 | 默认最近 5 份、最多 20 份，不是全历史补齐；独立展品索引抓取、全表单自动解析尚未完成。无法确定的事件进入 REVIEW_REQUIRED |
| Canonical ingestion | 证据归属 / 时点、数值 token 与比例、单位注册、期间、fact version 校验；历史证据可与当前披露比较 | 非结构化语义需要用户复核；AI 候选不得直接晋升 canonical |
| Massive | 完整分页、OHLCV 检查、AM/Q WebSocket 认证/恢复、拆股时点调整、SPY/板块对齐、20 日同时间量比、VWAP、窗口收益 | 代码及模拟契约已验证；真实权限、停牌覆盖和持续行情验收待账户；盘前盘后不执行 |
| Fundamental | 指引中值变化、利润率 bps、FCF、回购/市值、摊薄比例、交易价差、内部人集群 | 公司特有指标、完整 YoY/QoQ 加速度、跨报表复核仍需扩展注册与解析 |
| Reaction | XNYS 版本化日历、假日/DST/提前收市；原始/SPY/板块收益、量比/VWAP/gap/range 与 30m/close/next-open | 缺分钟不填补，历史/延迟不冒充实时；见 INTEGRATIONS.md 计算口径 |
| Family rules | v1.0.1 materiality 分层、候选/风险/背景角色、各家族的入场条件与默认等待期限 | 8–15% 需要额外确认、EXTENDED override 和未知 corporate subtype 缺乏具体公式，保守阻止 READY；不擅自配置收益优化阈值 |
| State machine | 合法边检查、显式用户入场、失效、忽略、持仓管理、退出；终态不自动复活 | 跨新披露自动关联已有 Thesis 的完整语义判别未实现；可用新版本事件和快照重新计算 |
| Portfolio | IBKR 分页持仓、现金账本与净值对账，conid 核验，持仓失效计划，风险/集中度/现金 sizing，失败即阻断 | 当前支持 USD 多头股票；其他币种/资产或未知成本风险需复核；实际账户未验收 |
| Execution | 本地演示闭环；另有 IBKR paper 草稿/what-if/显式确认/警告回复/取消 API，持久防重、部分成交和执行对账账本 | API 实现与模拟测试完成，真实账户仍待验收；UI 可查看券商账本，券商持仓与机会状态/绩效的完整自动闭环仍未验收；live 禁用 |
| Outcome / learning | 演示 entry/exit 净损益/费用/R；新增历史日线 1/5/10/20D、MFE/MAE、可确定基准收益/滑点的计算与存档 API | 日内入场当日极值排除；不含分红；不推测未知基准入场价；与真实券商学习库自动汇总待扩展 |
| Historical analog | 家族匹配、禁止未来 outcome、样本不足提示、描述统计 | 高级公司/板块/趋势/估值匹配未完成；没有内置真实类比样本 |
| AI independence | 纯函数核心不发出 AI 请求；AI fields 从输入核心哈希剔除；OFF/ASSIST 导出一致 | DeepSeek 候选提取/独立解释、缓存/预算/脱敏边界、人工复核晋升已实现；真实提取质量验收按用户要求后置 |
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

## 集成 v2 补充

详细配置、计算范围及账户待验收项以 [INTEGRATIONS.md](INTEGRATIONS.md) 为准。旧示例与旧 API 契约中关于“仅适配器骨架”的说明已被本节替代。

## 个人研究补充

新增独立研究状态、股票/事件偏好、DeepSeek、EX-99 归档、候选复核、可选研究轮询及本机提醒。个人使用与 AI 的实际边界见 [PERSONAL-RESEARCH.md](PERSONAL-RESEARCH.md)；真实案例及长期验收后置，不影响开发和合成验证继续。

## 个人机会看板增补（2026-10-03）

已实现共享事件影响判断：仅用通过校验的前后指标变化给出方向，保留未复核、缺行情与不确定状态；提供交易日观察窗口和不可覆盖的判断快照。今日概览展示摘要，研究动态负责证据与事实复核，机会研究展示持续判断及失效条件。方向颜色及页面流程见 [个人研究指南](PERSONAL-RESEARCH.md)。

尚未完成：市场一致预期接入、概率/收益区间校准、判断结果的收益回填与准确率评估、上次访问以来的专用变化报告。已有 outcome 计算 API 不等于事件方向模型已完成效果评估。Massive 历史接口已实测，最新数据权限受限，详见 [实际接口验证](MASSIVE-LIVE-VALIDATION.md)。这些能力增补不改变生产门禁和真实交易关闭状态。
