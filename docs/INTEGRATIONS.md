# Massive / IBKR 集成 v2

本次交付包含可调用的适配器、计算管道、持久券商订单账本、应用 API 与离线契约测试。**没有 Massive Key 或 IBKR 账户时，不能验证真实连通性、订阅权限或券商成交行为。** UI 的“适配器已实现”与“待配置 / 待实测”分开显示。默认不启动轮询，不提交外部订单。

## 安装与运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-integrations.txt
.venv/bin/python -m usoe --demo --port 8787
# 独立真实数据工作区（不加 --demo）
.venv/bin/python -m usoe --port 8788
```

设置页“运行无账户自检”不读取凭证、不访问外部网络、不写入真实市场或组合快照。可以立即检查计算和部分成交逻辑。完整测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 配置

仅编辑本机 `.env`；不在网页输入或显示凭证。已有 SEC 联系信息继续有效。

| 变量 | 用途 / 默认值 |
|---|---|
| `MASSIVE_API_KEY` | Massive 自有 API Key；空值禁止请求 |
| `MASSIVE_DATA_MODE` | `historical` 默认；按实际订阅选择 `delayed` 或 `realtime`。配置不能替代授权验证；时间戳仍要通过新鲜度检查 |
| `IBKR_BASE_URL` | `https://localhost:5000/v1/api`；此版本使用用户已登录的 Client Portal Gateway，会话与 cookie 仅在进程内 |
| `IBKR_ACCOUNT_ID` | 用户明确配置的账户；账户不匹配或 selectedAccount 不一致时阻断，不自动切换账户 |
| `IBKR_PAPER_ENABLED` | 默认 `false`；显式 `true` 才允许纸面订单，且必须同时通过 DU 账号前缀及 DEMO/isPaper 元数据核验 |
| `USOE_CA_BUNDLE` | 可选可信 CA 链绝对路径，用于 Gateway TLS；绝不关闭 TLS 校验 |

云端 IBKR OAuth 注册/授权握手不属于此 Gateway 适配器；没有账户时也不会建立授权会话。真实资金订单始终关闭。

配置完成后可选：

```bash
.venv/bin/python -m usoe --port 8788 --poll-sec 300 --poll-integrations 60
# 订阅具体证券的 AM / Q（需要 delayed 或 realtime 模式及相应权限）
.venv/bin/python -m usoe --port 8788 --poll-integrations 60 --stream-symbols AAPL,SPY,XLK
```

轮询负责更新组合、行情和机会状态，**不创建、确认或取消订单**。WebSocket 认证成功后才订阅；断线显示 recovery_required，恢复时重新拉取 REST。WebSocket 缓冲用于观察；决策快照始终由完整 REST 窗口计算，不把断线后的零散帧拼成可执行行情。

## Massive 计算约定

- 分页跟随 `next_url`，只允许官方 HTTPS 主机；检查循环、安全页数上限、空结果、OHLCV、重复和时间顺序。所有分页完成才返回成功。
- 拉取原始未复权分钟数据，按**观察时点已经生效**的拆股统一股票、SPY 与板块 ETF 的价格/成交量。未来拆股不改写历史观察；分红 API 可读取，当前收益为价格收益、不含分红。
- XNYS 日历由锁定版本 `exchange_calendars` 提供，保存日历版本、假日、夏令时和提前收市。NYSE 常规时段用于本版美股对齐，交易所特殊例外仍需账户数据验收。
- 对齐三组已完成分钟；不填补没有成交的分钟。缺失可能是无成交，也可能是数据缺口，因此会要求复核并阻止 READY。
- VWAP 使用供应商分钟 VWAP × 成交量加权，不用 OHLC 均价替代。常规时段事件从事件后第一个完整分钟起计算；盘前/盘后事件从对应后续常规开盘起计算。
- 量比使用事件前 20 个完整交易日的**相同已开盘分钟数**，提前收市不足相同长度的样本不使用；不足 20 个样本时阻断。
- 计算原始/SPY/板块超额收益、开盘缺口、事件日区间、VWAP 关系、30 分钟/事件收盘/下次开盘窗口、各事件族失效参考价。没有可验证的 insider 集群日期不猜测失效价。
- REST NBBO 时间由纳秒转换；WebSocket AM/Q 为毫秒。报价缺失、过期、交叉或未来时间均不能作为实时可执行输入。
- 盘前/盘后仅有扩展时段观察、尚无所需常规窗口时保留不完整状态；本版不提供盘前/盘后入场执行。
- 行情 `market-2` 快照具有输入引用、日历、覆盖率、quality_errors 和哈希。旧规则版本与已有回放结果保留。

## IBKR 对账与纸面订单

账户同步依次检查会话、账户、分页持仓、summary、ledger、订单和执行。净值必须与现金 + 支持的股票市值对得上；币种、证券映射、现有持仓失效计划、同催化分类、挂单占用任一不确定时阻断。当前支持 USD 多头股票；其他币种/空头/衍生品进入复核，不把它们当成零风险。

设置页支持指定并核验 conid，以及填写现有持仓失效价/事件族。变更后立即让旧组合快照失效，必须重新同步。风险计算涵盖可用现金、购买力、单票/板块/同催化集中度、默认风险预算和总未平仓计划风险。

`broker_tickets` 与本地演示 `order_intents` 完全分开。账户快照是实际持仓权威来源；券商回报不会在演示 positions 表里伪造成交。券商纸面 API 提供：

1. 用户基于 READY、新鲜对账组合和已验证 conid 创建 DAY 限价草稿（BUY）；SELL 限制为已对账持仓数量并要求退出原因。
2. 用户确认 `preview`，执行券商 what-if；准备好后另一次确认 `submit`，再次检查时效和风险。
3. 提交前持久记录 `SUBMITTING` 与稳定 cOID；同一个幂等请求不会重复创建，已预留的变更不会自动重试。
4. 接单仅标记 ACKNOWLEDGED；券商警告保持 AWAITING_REPLY，用户必须核对消息及 reply_id 后显式确认；不自动抑制警告。
5. 超时或重启期间结果不明保持 UNKNOWN / SUBMITTING，先与券商对账；不得创建新订单绕过未知结果。
6. 执行按 execution_id 去重，累计数量、成交均价、佣金和滑点；部分成交与部分成交后取消分别保留。数量不一致或执行更正进入 RECONCILIATION_REQUIRED。
7. 取消请求保持 CANCEL_PENDING，直到后续券商快照确认。已归档执行不受券商滚动查询期限影响，但离线期间漏掉且已超出查询范围的执行需人工补核。

券商账户元数据、账号与会话信息在归档前去除/替换；Massive next_url 中密钥去除。这里保存的是**脱敏后规范化 JSON**及其哈希，并非逐字节网络包；SEC 原文归档仍保持原始字节。审计、执行、回执与计算输入不可变追加。

纸面提交目前提供 API 工作流；界面提供订单/成交记录查看，不把隔离演示的“模拟成交”按钮改成外部下单按钮。券商账本、机会 MANAGE/EXITED 自动关联及其家庭绩效汇总尚未完成账户验收，不能当成商用交易闭环。

## 历史结果计算

`POST /api/v1/market/outcomes` 拉取股票与 SPY 日线，返回 1/5/10/20 个完整交易日收益、可确定时的基准超额、MFE/MAE、净损益、费用、R 倍数和入场滑点。保存完整输入供复核。

必须明确 `price_basis=split_adjusted_as_of`；输入入场/退出价、股数、计划价应与观察时点拆股口径一致。它是研究计算接口，不把调用者输入当成券商成交证明。当前 MFE/MAE 仅覆盖入场后完整交易日；日内成交所属交易日因含成交前极值而排除。不能确定的基准入场价返回 null，不用当日开盘价冒充日内成交时点。尚未达到的 horizon 返回 null。当前无含分红总回报、精确成交后逐笔路径或自动更新真实历史类比库。

## 仍需凭证/实际运行的验收

真实 Massive 连通性、实时权限和停牌/异常交易覆盖；IBKR Gateway 登录、实际 paper 正常/拒单/部分成交/取消及断线恢复；真实 Golden 100、14 日 SEC 与 20 日 Shadow。当前统一保持 `PRODUCTION_BLOCKED`。

## 官方接口依据

- [Massive REST 股票聚合](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
- [Massive WebSocket 分钟聚合](https://massive.com/docs/websocket/stocks/aggregates-per-minute) 与 [报价](https://massive.com/docs/websocket/stocks/quotes)
- [IBKR 账户元数据](https://www.interactivebrokers.com/docs/web-api/api-reference/trading/trading-portfolio/get-all-accounts)
- [IBKR Web API 官方文档](https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/)
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)
