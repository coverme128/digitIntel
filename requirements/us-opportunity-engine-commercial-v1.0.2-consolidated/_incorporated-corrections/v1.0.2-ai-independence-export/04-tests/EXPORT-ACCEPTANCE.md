# Export Acceptance

## JSON
- schema valid
- evidence refs 完整
- rule_version 存在
- core hash 存在

## Markdown
- 所有核心决策部分存在
- 不依赖 AI 文本
- 可直接复制给外部 AI

## CSV
- stable headers
- deterministic values
- 无 AI prose
- 支持 batch export

## Hard Gate

所有 export 格式必须在：
`AI_MODE=OFF`
下完整可用。
