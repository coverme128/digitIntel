# API Contracts

## Read APIs

`GET /api/v1/today`
- opportunities
- ready
- position attention
- invalidated
- filtered event count

`GET /api/v1/opportunities`
filters:
- state
- family
- sector
- symbol

`GET /api/v1/opportunities/{id}`
returns:
- event
- evidence
- facts
- calculations
- reaction
- analogs
- triggers
- invalidation
- risk flags
- transitions

`GET /api/v1/portfolio`
- snapshot
- positions
- exposures
- attention items

`GET /api/v1/history`
- exited
- invalidated
- ignored

## Write APIs

`POST /api/v1/opportunities/{id}/watch`
`POST /api/v1/opportunities/{id}/ignore`
`POST /api/v1/order-intents`
`POST /api/v1/order-intents/{id}/confirm`
`POST /api/v1/positions/{id}/exit-intent`

## Safety

所有 broker write endpoint：
- idempotency key
- CSRF/session protection
- user confirmation
- audit log
- no AI direct invocation
