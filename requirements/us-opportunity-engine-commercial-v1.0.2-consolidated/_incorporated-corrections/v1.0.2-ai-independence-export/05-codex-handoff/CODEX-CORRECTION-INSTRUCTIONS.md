# Codex v1.0.2 Correction Instructions

## Required changes

1. 抽离所有 AI-dependent core logic
2. Introduce `CoreOutput`
3. Add `AI_MODE=off|assist`
4. OFF 模式完整可用
5. AI Assist 只消费 CoreOutput，不得修改
6. Add `core_output_hash`
7. Add JSON / Markdown / CSV export
8. Add parity regression tests
9. Add AI failure isolation
10. Add UI AI-mode setting

## Must not change

- sources
- opportunity taxonomy
- state machine semantics
- personal alpha objective
- portfolio rules
- validation ladder

## New gates

- `AI_OFF_FULL_FUNCTION_READY`
- `CORE_OUTPUT_PARITY_READY`
- `DECISION_EXPORT_READY`
- `AI_FAILURE_ISOLATION_READY`

Final:
`PERSONAL_ALPHA_CORE_AI_INDEPENDENT_READY`
