# AI Mode Configuration

Required:
`AI_MODE=off|assist`

Optional:
- `AI_PROVIDER=openai|anthropic|deepseek|external|none`
- `AI_EXPLANATION_ENABLED=true|false`
- `AI_EXTRACTION_CANDIDATES_ENABLED=true|false`

## OFF

- core pipelines 不得发出必需 AI 请求
- core jobs 不得等待 AI queue

## ASSIST

- AI jobs 与 core jobs 解耦
- core state 先生成
- explanation 后生成

切换 OFF ↔ ASSIST：
- 不要求 core recompute
- 不迁移 opportunity state
- 不产生新的 domain rule version
