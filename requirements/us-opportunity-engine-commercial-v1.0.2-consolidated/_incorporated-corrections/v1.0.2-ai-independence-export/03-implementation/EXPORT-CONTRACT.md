# Export Contract

## API examples

- `GET /api/v1/opportunities/{id}/export?format=json`
- `GET /api/v1/opportunities/{id}/export?format=markdown`
- `GET /api/v1/opportunities/export?state=READY&format=csv`
- `GET /api/v1/portfolio/export?format=json`
- `GET /api/v1/outcomes/export?format=csv`

## JSON envelope

Required:
- export_version
- exported_at
- ai_mode
- core_output_hash
- rule_version
- source_snapshot
- payload

## Markdown

必须由 CoreOutput 确定性生成。
AI 内容若包含，只能放在：
`Optional AI Commentary`

## CSV

不得包含 AI prose。

## Integrity

`core_output_hash` 只对 normalized core payload 计算。
AI fields 必须排除。
