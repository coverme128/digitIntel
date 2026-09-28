# 验证记录 · 2026-09-28

## 自动化

最终本地执行：

```text
python3 -m unittest discover -s tests -q
Ran 77 tests
OK
```

其中 `FamilyRegression100` 包含 100 个独立合成家族场景（30 / 15 / 15 / 10 / 10 / 10 / 10）。这些不是需求中的真实 Golden 100，不用于证明盈利能力。

覆盖：

- 指引中值、利润率 bps、materiality 边界、零基数、期间/单位不一致。
- 交易会话、节假日、提前收盘、时区、缺日历、过期 / 延迟 / 未来行情、开盘前五分钟。
- Extended / adverse / caution、非入场角色、无规则 corporate subtype。
- 风险预算、板块 / 单票 / 催化集中度、过期 broker、购买力未知、失效价格缺失。
- 状态和 actor 限制、重复 accession、演示/真实环境隔离、原始数据及计算不可覆盖。
- 订单二次确认、幂等冲突、取消、过期、并发确认只有一次成交、退出账本与净损益。
- AI OFF / ASSIST 核心与导出哈希一致；AI 字段不进入 core snapshot hash。
- JSON / Markdown / CSV 全范围导出、CSV 公式注入转义。
- Host / DNS rebinding、防跨站请求、CSRF、会话隔离、多标签页会话复用、目录遍历阻断。
- SEC 身份 / 原文归档 / 去重、source failure 降级、Form 4 排除非公开市场买入、XBRL 排除未来修订。
- Massive 空窗口 / 重复 timestamp 拒绝，IBKR 只读调用与账号脱敏。
- 数字与原文不一致、未知 metric、快照 ID 冲突、跨证券行情错配。

Python compileall 和 JavaScript `node --check web/app.js` 均通过。

## 浏览器验证

在 Codex 内置浏览器中验证：

- 今日概览和完整详情，含证据原文链接、计算、条件列表、失效、规则与快照。
- 创建 NOVA.D 的 **10 股 × 106 美元**纸面草稿，最大计划亏损 **60 美元**，资金占用 **1,060 美元**。
- 二次确认进入 MANAGE；组合现金从 78,000 变成 76,940。
- 手动退出模拟 **110 美元、手续费 2 美元**；再次确认生成 **38 美元净损益、0.6333R**，历史页显示 EXITED。
- 390px 移动端：内容宽度不超过 viewport；修正导航滚动条、标题和按钮布局。
- 浏览器应用脚本错误日志为空。
- 按 NOVA 搜索只返回一条 READY，CSV 导出链接同步携带 q=NOVA，范围一致。

浏览器验收写入的开发演示库单独保存在 `data/development-acceptance-*.sqlite3`。最终用户演示库重新按相同固定样例初始化，保留一个 READY 入口方便体验。开发库不是正式历史 Golden 数据。

最终演示数据库：SQLite integrity_check = ok，外键检查无异常，审计哈希链有效；7 个机会原输入重放全部一致。使用 SQLite backup API 复制到临时数据库后，审计与 7 个机会重放仍通过。这是本地备份恢复测试，不等于生产运营恢复演练。

## SEC 官方连通性

使用用户在本机配置的 SEC User-Agent，未输出邮箱或任何凭证。

1. `data.sec.gov/submissions/CIK0000789019.json` 实际返回 MSFT / 正确 CIK，身份校验通过。
2. `python3 scripts/sec_smoke.py` 在独立测试库完成 submissions → 一份实际 primary document → companyfacts 的只读归档链路：

```json
{"audit":true,"companyfacts_archived":true,"filings_archived":1,"opportunities_created":0,"status":"REVIEW_REQUIRED"}
```

完整归档成功，但未经验证的原始披露不会自动形成机会。此单次检查不等于 14 个交易日 SEC 稳定性门禁。

Massive 真实订阅、IBKR 实际账户会话没有提供；相应适配器通过本地契约测试，未声称通过真实账户验收。

## 仍未通过的生产条件

参见 `docs/IMPLEMENTATION.md`。真实 Golden 100、至少 20 个交易日 Shadow、券商 paper 全流程、实时窗口、授权核验和生产运营验收均未完成；因此状态保持 `PRODUCTION_BLOCKED`。

## Massive / IBKR 集成 v2（2026-09-28）

- `.venv/bin/python -m unittest discover -s tests -q`：**136 tests，全部通过**。包含 59 个新增集成/HTTP 检查；原有用例继续通过。
- 重点：分页和恶意 next_url、凭证脱敏、日期范围、缺分钟、不完整 VWAP、延迟/过期报价、拆股时点、日历 DST/提前收市、真实形状账户响应到组合快照、部分/重复/冲突执行、纸面校验、无响应不重试、跨账户订单隔离、TLS 防降级与 GET 429 重试。
- `make check`、`git diff --check` 通过。
- 原演示库 7 个机会重放保持相同哈希；SQLite/外键/审计链检查通过。更新前备份 `/private/tmp/usoe-before-integrations-20260928.sqlite3`。
- 在应用浏览器实际打开设置页并点击“运行无账户自检”：9 项通过，网络请求 0，VWAP=105、量比=2、板块超额=4%、风险容量=4 股、部分成交=2/5。全部数值为合成样例，不构成真实 API 验收。
- 无 Massive Key / IBKR 账户，未对外发送任何订单。具体范围和仍需账户的检查见 `INTEGRATIONS.md`。
