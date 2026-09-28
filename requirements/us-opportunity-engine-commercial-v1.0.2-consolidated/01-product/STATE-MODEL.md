# Opportunity State Model

## States

### DISCOVERED
发现原始事件，尚未完成验证。

### VERIFIED
原始证据已确认，字段可追溯。

### QUALIFIED
事件通过 materiality 和 data-quality gate。

### WATCH
存在潜在机会，但 entry condition 未满足。

### READY
预定义 entry conditions 已满足。

### ENTERED
用户明确记录/执行进入。

### MANAGE
已有仓位处于 thesis monitoring。

### EXITED
用户已退出，保留 outcome。

### INVALIDATED
机会逻辑被规则破坏。

### IGNORED
用户主动忽略。

## State Transition Rules

- `DISCOVERED → VERIFIED`：evidence gate pass
- `VERIFIED → QUALIFIED`：materiality pass
- `QUALIFIED → WATCH`：opportunity qualification pass
- `WATCH → READY`：entry trigger pass
- `READY → ENTERED`：only explicit user action
- `ENTERED → MANAGE`：position created/reconciled
- `WATCH/READY/MANAGE → INVALIDATED`：invalidation rule pass
- `MANAGE → EXITED`：user exit or broker reconciliation

禁止：
- VERIFIED 直接 ENTERED
- WATCH 自动 ENTERED
- AI 文本触发交易状态
