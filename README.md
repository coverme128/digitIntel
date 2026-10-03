# US Opportunity Engine · v1.0.2

一个本地运行、证据优先、AI 独立的美股事件研究与决策工作区。根据 `requirements/us-opportunity-engine-commercial-v1.0.2-consolidated/` 实现。

**当前交付：可运行的本地工程版本，不是 Commercial V1 上线认证。** 合成演示与真实数据分库；真实交易接口关闭。完整范围及未完成的生产能力见 [实现覆盖表](docs/IMPLEMENTATION.md)。

## 启动

基础演示只需 Python **3.11+**，不依赖 npm、LLM 或数据库服务器。完整行情日历和 WebSocket 使用 `requirements-integrations.txt` 中的可选依赖，见 [集成指南](docs/INTEGRATIONS.md)。

```bash
cd /Users/goterra/Documents/digitIntel
python3 -m usoe --demo
```

访问 [http://127.0.0.1:8787](http://127.0.0.1:8787)。

演示工作区使用**全部虚构**的 `.D` 公司、价格与事实，固定回放时点为 `2026-09-25 11:30 America/New_York`，便于重复演示。默认包含 READY、WATCH、反应过度、失效、融资风险与并购背景案例。数据落在 `data/demo.sqlite3`，刷新和重启不会丢失。

真实只读研究工作区：

```bash
python3 -m usoe --port 8788
```

访问 [http://127.0.0.1:8788](http://127.0.0.1:8788)，使用 `data/shadow.sqlite3`，初始允许 0 个机会。不会自动将演示数据放入真实工作区。

## 目前可以做什么

- 在中文界面浏览今日概览、研究动态、机会研究、机会详情、观察列表、组合、证据中心、历史复盘和设置。
- 真实工作区用方向摘要与完整判断跟踪事件；演示机会列表支持按状态、事件族、证券名称筛选。检查基本面计算、相对 SPY / 板块反应、入场条件与失效条件。
- 使用版本化的确定性规则评估指引、回购、内部人买入、主动股东、公司事件、融资和并购。
- 追溯标准化事实到归档原文、定位与 SHA-256；重放原始计算并核对输出哈希。
- 演示模式中完成“草稿 → 二次确认 → 纸面成交 → MANAGE → 退出预览 → 确认 → EXITED”；保存 Thesis 与不可变结果账本。
- 导出 JSON、Markdown、CSV；包含规则版本、快照、AI 模式和核心 SHA-256。无需 AI 即可交给其他分析工具使用。
- 将 SEC 官方披露与 companyfacts 归档到待复核队列；使用 Massive 分页行情、WebSocket、日历/拆股/基准对齐计算和 IBKR 组合对账适配器。
- 在本地开启 SEC 轮询，查看审计链、运行指标、备份及重放验证。

## 数据源配置

本地 `.env` 已配置本次提供的 SEC 联系信息，已被 `.gitignore` 排除，不应提交或分享。示例格式见 `.env.example`。**程序从不在界面或日志输出联系邮箱、API key、券商账号。** 修改配置后重启进程。

```dotenv
SEC_USER_AGENT=USOpportunityEngine/1.0 contact your-email@example.com
MASSIVE_API_KEY=
MASSIVE_DATA_MODE=historical
IBKR_BASE_URL=https://localhost:5000/v1/api
IBKR_ACCOUNT_ID=
IBKR_PAPER_ENABLED=false
AI_MODE=off
```

1. 在真实工作区“设置与数据源”注册证券代码、10 位 CIK、公司名及板块。
2. 点击“同步最近披露”。SEC 返回的 ticker / CIK 必须一致；披露按 accession 去重，保存 accepted timestamp、原文与哈希。
3. 披露进入“证据中心”的待复核队列。原始文本或 AI 文本不会直接变成机会；规范化事实包必须通过证据、数字、期间、单位、市场窗口校验。
4. Massive 需要用户自己的数据订阅。支持分页行情、拆股调整、SPY/板块对齐、VWAP/同时间量比/收益计算和可选 AM/Q WebSocket；缺窗口或权限时阻断 READY。
5. IBKR 同步账户、分页持仓、摘要、现金账本、订单与执行，并完成 conid/现金/净值/风险计划对账。纸面订单 API 已实现，默认关闭；真实资金提交关闭。Gateway 登录由用户完成；默认验证 TLS。如使用自建 CA，通过 `USOE_CA_BUNDLE=/absolute/path/ca.pem` 提供信任链，**不要关闭证书验证**。

可选 SEC 定期抓取（最小间隔 60 秒，默认建议 300 秒；需有效配置与注册证券）：

```bash
python3 -m usoe --port 8788 --poll-sec 300
```

轮询只更新数据和规则评估，不下单。公开 SEC 数据抓取仍可能被访问策略、代理或网络限制拒绝；失败显式标记 `DEGRADED`，不填充合成结果。

## 无账户 API 自检

在“设置 → API 对接与计算验收”点击“运行无账户自检”，无需凭证即可验证行情、组合风险和部分成交逻辑。接口与安装、账户验收步骤见 [Massive / IBKR 集成指南](docs/INTEGRATIONS.md)。

## 使用与开发

```bash
# 所有单元 / 契约 / HTTP 集成测试（需要允许本机随机端口）
python3 -m unittest discover -s tests -v

# Python / JS 语法检查（仅检查 JS 时需要 Node）
make check

# 重放当前工作区的全部机会
python3 scripts/manage.py --db data/demo.sqlite3 replay

# SQLite、外键及审计链检查
python3 scripts/manage.py --db data/demo.sqlite3 verify

# 在线一致性备份（不会覆盖已有目标文件）
python3 scripts/manage.py --db data/demo.sqlite3 backup /tmp/usoe-backup.sqlite3
```

更多维护命令、恢复步骤、规范化导入与 API 见 [操作手册](docs/OPERATIONS.md) 和 [API / 数据契约](docs/API.md)。

## 实现选择

需求中的 Next.js / TypeScript、PostgreSQL、BullMQ、S3 是推荐架构。此版本选择 **Python 标准库 HTTP API + SQLite/WAL + 原生 HTML/CSS/JavaScript**，使单用户本地安装可直接运行，同时保持 Raw / Canonical / Derived / Presentation 分层与纯函数引擎。原始资料以不可变 BLOB 保存；重放输入与规则快照一并保留。

它不是多租户服务；仅监听 `127.0.0.1`，不应直接暴露公网。生产扩展、真实交易验证、完整数据管道与权限体系见实现覆盖表。

## 已冻结的边界

- AI Off 完整保留核心规则与导出；DeepSeek 已接入独立候选/解释流程，未配置 Key 时明确降级；AI Off 不发出模型请求。
- READY 不是自动买入。资金和风险计划必须经过显式二次确认；隔离演示的本地模拟与 IBKR 纸面 API 分开；后者必须配置、核验 paper 账户并逐次显式确认。真实资金提交关闭。
- 无具体 subtype 规则的公司事件不得 READY；融资摊薄为 POSITION_RISK；M&A 为 CONTEXT_ONLY。
- 不以模拟案例替代真实 Golden 100；不以一次回归代替 14 / 20 个交易日运行验证。
- 每次正式规则升级需要新版本与迁移说明；不得覆盖旧计算或用未来数据重放历史。

## 官方接口参考

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)：submissions 与 companyfacts。
- [SEC Developer Resources](https://www.sec.gov/about/developer-resources)：Fair Access 与 User-Agent 规则。
- [Massive Custom Bars](https://www.massive.com/docs/rest/stocks/aggregates/custom-bars)：历史 OHLCV 聚合接口。
- [IBKR Web API](https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/) 与 [Positions](https://www.interactivebrokers.com/docs/web-api/v1/endpoints/portfolio/positions)：只读账户与持仓。

本工具用于研究和记录，不构成投资建议；当前规则未被证明具备盈利能力。

## 个人研究与 DeepSeek

真实工作区由“今日概览 → 研究动态 → 机会研究”组织：概览展示方向摘要与待办，研究动态（原每日研究）负责披露和事实核对，机会研究持续跟踪完整依据与失效条件。不接 IBKR 也能选择关注股票和事件、复核 AI 候选及查看本机提醒。DeepSeek 提取和解释独立于核心规则，Key 配置在本机 `.env`，AI Assist 和自动提取分别控制。真实案例验收暂后置。

完整使用流程、模型配置、SEC 展品、人工核对与 `--poll-research` 见 [个人研究指南](docs/PERSONAL-RESEARCH.md)。

方向颜色采用红色偏多、绿色偏空、黄色分歧、灰色证据不足或历史/失效；保留文字和复核状态。颜色用于研究筛选，不等于买入指令。当前判断规则未经过历史效果校准；真实行情访问仍受订阅权限限制，见 [Massive 实际接口验证](docs/MASSIVE-LIVE-VALIDATION.md)。
