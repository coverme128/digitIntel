# External Reference Sources

本文件仅用于实现时核对外部契约；实际代码应以部署时最新官方文档为准。

## SEC
- EDGAR APIs:
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Developer resources / fair access:
  https://www.sec.gov/about/developer-resources

要点：
- data.sec.gov API 无需 API key
- submissions / XBRL 是核心
- 必须遵守 fair-access policy

## Massive
- WebSocket:
  https://massive.com/docs/websocket/quickstart

要点：
- realtime stock trades/quotes/aggregates
- REST / WebSocket / flat files 分工明确

## Interactive Brokers
- Web API:
  https://www.interactivebrokers.com/docs/web-api/introduction
- Market data:
  https://www.interactivebrokers.com/docs/web-api/api/web-api/obtaining-market-data
- Portfolio positions:
  https://www.interactivebrokers.com/docs/web-api/v1/endpoints/portfolio/positions

要点：
- 可读取市场数据、账户、持仓并管理交易
- 实时市场数据受账户订阅和 market data line 限制
