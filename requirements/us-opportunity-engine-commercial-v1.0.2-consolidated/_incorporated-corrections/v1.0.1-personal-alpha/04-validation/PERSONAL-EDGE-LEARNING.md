# Personal Edge Learning

## Principle

系统长期要回答：

> 哪类机会对这个账户和这个用户真正有效？

## Store Per Trade

- opportunity family
- event subtype
- rule version
- entry trigger
- entry price/time
- invalidation
- exit price/time
- realized P&L
- MFE
- MAE
- holding days
- sector context
- portfolio context
- exit reason

## Review Cadence

- every 10 completed trades: data quality review only
- every 30 completed trades: provisional family review
- every 100 family trades: formal rule review

## Rule Change

不得让模型自动改 production rule。

Process:
1. detect performance issue
2. propose hypothesis
3. backtest/replay
4. shadow
5. approve new rule version
6. compare forward results

## Kill Rule

A family can be disabled when:
- persistent negative expectancy
- unacceptable drawdown
- high false-positive cost
- poor execution feasibility

Disable rather than “AI tweak until it wins”.
