# Core Output Parity Tests

对每个 Golden fixture：

1. `AI_MODE=OFF` 跑 deterministic pipeline
2. 保存 CoreOutput
3. `AI_MODE=ASSIST` 跑同一输入
4. 去除 optional AI fields
5. 标准化
6. 比较 CoreOutput
7. 比较 `core_output_hash`

要求：
**100% identical**

覆盖：
- Earnings / Guidance
- Buyback
- Insider Buy
- Activist
- Material Corporate
- Financing Risk
- Context-only M&A
- Portfolio hard block
- Invalidation
- Outcome

任何 mismatch：
`AI_CORE_PARITY = FAIL`
并阻断发布。
