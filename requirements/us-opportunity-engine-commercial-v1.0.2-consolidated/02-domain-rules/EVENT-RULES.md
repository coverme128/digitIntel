# Event Rules

## 1. Materiality Framework

事件通过以下任一条件可进入进一步计算：

### Quantitative
- guidance midpoint change absolute >= configurable threshold
- buyback authorization / market cap >= threshold
- financing size / market cap >= threshold
- transaction value / market cap >= threshold
- insider open-market purchase value >= absolute + relative threshold
- ownership change >= threshold

### Structural
以下事件不依赖纯金额阈值：
- guidance withdrawn
- CEO/CFO departure
- bankruptcy / going concern
- activist 13D
- definitive merger agreement
- material restatement
- delisting / trading halt related event

## 2. Required Evidence

每个 Event 必须保存：
- source_id
- filing accession number
- form type
- filing timestamp
- document URL
- exhibit URL when relevant
- source excerpt / structured fact location
- extracted facts
- parser version
- AI model/version if AI used

## 3. Duplicate Rules

同一 accession + event_type + canonical security：
- 默认同一 event
- amendment 建立 parent_event_id
- 不得重复生成多个新机会

## 4. Temporal Rules

所有计算使用：
- SEC accepted timestamp
- U.S. market session calendar
- premarket / regular / after-hours session classification

禁止只使用“filing date”忽略 accepted time。
