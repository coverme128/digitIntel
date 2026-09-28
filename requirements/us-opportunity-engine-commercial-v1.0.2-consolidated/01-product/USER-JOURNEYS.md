# User Journeys

## Journey A — 新机会

1. SEC 出现新 filing。
2. Event Detector 标记 material event。
3. Evidence Validator 确认原始证据。
4. Domain Engine 计算 magnitude。
5. Market Reaction Engine 计算事件前后价格与量。
6. Opportunity Engine 生成 `WATCH`。
7. 用户打开 Detail。
8. 用户可：
   - Ignore
   - Keep Watch
9. 如果 entry rule 满足，状态变为 `READY`。
10. 用户决定是否 Enter。
11. 进入后建立 Position Thesis Snapshot。

## Journey B — 事件很大但市场已经充分反应

例：
- Guidance +8%
- After-hours +19%

处理：
- Event = MATERIAL
- Opportunity = `WATCH` 或 `IGNORE`
- Reason = reaction already extended

系统不得因为“好消息”自动进入 READY。

## Journey C — 机会失效

例：
- READY 后股价跌回事件前基准
- 新 filing 撤回 guidance
- sector context 崩坏
- 时间窗口超时

处理：
- `INVALIDATED`
- 保存 invalidation reason
- 禁止删除历史机会

## Journey D — 已持仓出现新事件

1. 新事件进入 Position Monitor。
2. 对比 original thesis。
3. 分类：
   - SUPPORTS
   - NEUTRAL
   - WEAKENS
   - BREAKS
4. 若 BREAKS：
   - Position Attention
   - 用户必须 review
5. 系统不得自动卖出 V1 实盘仓位。

## Journey E — 进入交易

用户点击 ENTER 前必须看到：
- position size
- intended entry
- max planned loss
- thesis
- invalidation
- concentration impact

确认后：
- 可生成 order draft
- V1 默认仍需用户显式二次确认
