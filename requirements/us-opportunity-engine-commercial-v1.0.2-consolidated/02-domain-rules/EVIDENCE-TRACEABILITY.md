# Evidence & Traceability

## 原则

每个用户看到的具体事实，都必须能回到：
`Fact → EvidenceSpan → SourceDocument → Source`

## Evidence Levels

### E1 Canonical Official
SEC filing / exhibit。

### E2 Official Supplemental
公司 IR / official press release。

### E3 Calculated
基于 E1/E2 + market data 的确定性计算。

### E4 AI Interpretation
AI 对 E1-E3 的解释。

V1 Opportunity 的关键事实不得只依赖 E4。

## Required Lineage

保存：
- source hash
- fetched_at
- source timestamp
- parser version
- fact extractor version
- rule version
- calculation inputs
- calculation output

## Correction

发现事实错误时：
- 不覆盖旧结果
- 创建 corrected fact
- 标记 supersedes
- 重跑受影响 opportunity
