# Fundamental Inflection Rules

## 1. 核心思想

“好财报”不是规则。
必须计算“发生了什么变化”。

## 2. Standard Metrics

优先使用：
- Revenue
- Gross Profit / Margin
- Operating Income / Margin
- Net Income
- Diluted EPS
- Operating Cash Flow
- Free Cash Flow（统一自算口径）
- Cash
- Total Debt
- CapEx

## 3. Company-Specific Metrics

可通过 Metric Registry 加入：
- ARR
- RPO
- Backlog
- Bookings
- Subscribers
- Units
- Same-store sales
- ASP

必须：
- metric_id 固定
- source evidence 可追溯
- unit/period 明确
- 不允许 AI 临时发明 metric

## 4. Delta Types

- QoQ
- YoY
- sequential acceleration
- margin delta in bps
- guidance midpoint delta
- guidance range delta
- beat/miss only when consensus source exists

V1 不依赖第三方 consensus，因此 consensus beat/miss 不是核心必需规则。

## 5. Inflection

默认需要至少满足一种：
- growth acceleration >= threshold
- margin expansion >= threshold
- guidance direction reversal
- FCF sign / quality change
- balance-sheet risk materially reduced/increased

## 6. Quality Gate

数字必须通过：
- unit normalization
- period alignment
- filing vs exhibit reconciliation
- restatement awareness
