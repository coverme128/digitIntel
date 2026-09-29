# Massive 实际接口验证

验证完成时间：2026-09-29T01:01:19+00:00；最近已收盘交易日：2026-09-28。

使用本地已配置凭据；本文不包含 Key。未更改套餐、未下单。

| 测试 | 股票/日期 | 结果 |
|---|---|---|
| latest_session_minutes | AMD 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| latest_session_minutes | TSLA 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| latest_session_minutes | BABA 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| latest_session_minutes | SPY 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| latest_session_minutes | XLK 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| latest_session_minutes | XLY 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| actual_filing_market_calculation | AMD  | INCOMPLETE：DATA_MARKET_WINDOW_INCOMPLETE |
| prior_session_benchmark | SPY 2026-09-25 | SUCCEEDED：884 bars |
| prior_session_benchmark | XLK 2026-09-25 | SUCCEEDED：466 bars |
| prior_session_benchmark | XLY 2026-09-25 | SUCCEEDED：396 bars |
| latest_session_daily | AMD 2026-09-28 | FAILED：Upstream HTTP 403; authentication/entitlement required |
| provider_denial_detail | AMD  | 403：Your plan doesn't include this data timeframe. Please upgrade your plan at https://polygon.io/pricing |

结论：历史数据访问成功；最近交易日的日线、分钟线受套餐时间范围限制。上一轮最新买卖报价测试也返回 403。

AMD 实际 8-K 披露的行情计算运行后输出 complete=false、DATA_MARKET_WINDOW_INCOMPLETE。标的、SPY、板块 ETF 各缺少最新交易日 390 根常规时段分钟线。未用旧价填充，未批准候选事实或生成有效入场信号。

本轮源数据已归档，数据库审计链验证通过。需要开通相应时间范围权限后重新验证；未验证实时订阅可用。
