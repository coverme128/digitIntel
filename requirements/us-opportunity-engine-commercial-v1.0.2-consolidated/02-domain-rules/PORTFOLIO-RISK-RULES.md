# Portfolio Risk Rules

## 1. V1 目标

不是优化组合收益，而是防止一个好机会在错误组合里变成坏交易。

## 2. Required Checks

- position concentration
- sector concentration
- correlated holdings
- available cash / buying power
- current open risk
- duplicate thesis exposure
- earnings/event clustering

## 3. Hard Blocks

默认配置建议：
- stale broker data
- account reconciliation failed
- buying power unavailable
- security halted
- missing invalidation
- missing planned loss
- duplicate active order uncertainty

## 4. Soft Warnings

- sector concentration high
- same catalyst exposure high
- new position strongly correlated with existing holdings
- event occurs near another major portfolio catalyst

## 5. Position Sizing

V1 只提供 deterministic sizing worksheet：
- account equity
- max risk budget
- entry
- invalidation
- per-share risk
- max shares by risk
- max shares by concentration

系统不得以 AI 文本决定仓位。
