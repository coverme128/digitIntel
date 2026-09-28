# 本地操作与恢复手册

## 工作区隔离

- `data/demo.sqlite3`：合成资料与本地纸面交易，固定时点回放。
- `data/shadow.sqlite3`：真实只读数据，无自动交易。
- `data/sec-smoke.sqlite3`：可选官方 SEC 连通性验收，独立测试资料。
- `.env`：本机配置，权限 0600，不进入 Git；`data/` 同样忽略。
- 每个数据库的 workspace_mode 固定；已有数据库不能以另一模式启动。

默认服务器只绑定 127.0.0.1。不要用反向代理将此单用户服务直接暴露到外网。

## 服务启动与停止

```bash
python3 -m usoe --demo --port 8787
python3 -m usoe --port 8788
# 仅需要定时读取 SEC 时：
python3 -m usoe --port 8788 --poll-sec 300
```

Ctrl+C 正常停止 HTTP 服务；可选 worker 的下一轮轮询停止。处理中网络请求有超时，下一次启动会把遗留 RUNNING 任务标记为 INTERRUPTED。

服务不会创建系统 cron、LaunchAgent 或自动修改开机启动。

## 数据源失败

- **SEC**：检查 SEC_USER_AGENT 联系邮箱、网络与 Fair Access，日志/状态面板显示 DEGRADED。不要更换为非官方资讯填补。
- **Massive**：检查 API key、订阅、日期权限、空窗口、timestamp。历史数据不代表实时窗口通过。
- **IBKR**：在本地 Gateway 完成用户登录；检查受信任证书与账号匹配。账号 mismatch 硬阻断；不在日志显示账号。
- **AI**：ASSIST_UNAVAILABLE 只影响可选解释，OFF 下所有核心 API 继续可用。

单次官方只读验证（会向 SEC 发送已配置的 User-Agent；仅抓取公开 MSFT 测试样本）：

```bash
python3 scripts/sec_smoke.py
```

该脚本不会向真实工作区增加机会或持仓。仅 data.sec.gov 连通不等于 filing / exhibit / XBRL 全部链路通过；以脚本的完整结果为准。

## Universe 成员导入

CSV 列：

```csv
security_id,ticker,cik,issuer_name,sector,universe,valid_from
sec-msft,MSFT,0000789019,Microsoft Corporation,Technology,USER_WATCHLIST,2026-09-28
```

```bash
python3 scripts/manage.py --db data/shadow.sqlite3 universe universe.csv
```

`universe` 仅允许 USER_WATCHLIST、SP500、NASDAQ100；实际指数名单和历史日期必须来自有权使用的数据。不得把当前成分应用于过去回放。

## 备份与恢复

1. 在线备份使用 SQLite backup API，包含 WAL 中已提交数据：

   ```bash
   python3 scripts/manage.py --db data/shadow.sqlite3 backup /absolute/path/usoe-2026-09-28.sqlite3
   ```

2. 验证备份：

   ```bash
   python3 scripts/manage.py --db /absolute/path/usoe-2026-09-28.sqlite3 verify
   python3 scripts/manage.py --db /absolute/path/usoe-2026-09-28.sqlite3 replay
   ```

3. 恢复时先停止服务。不要直接覆盖原库，先保留原文件及相关 WAL/SHM；可用 `--db /absolute/path/backup.sqlite3` 在新的端口启动备份进行核验。
4. `.env` 不包含在数据库备份中，凭证应由用户独立安全保管。
5. audit 哈希链用于完整性检测，不代替外部可信签名或防管理员篡改方案。

## 规则与数据修订

- 不直接 UPDATE / DELETE 原始资料、事实、计算、转换或结果，数据库触发器禁止覆盖。
- 新数值用新 fact_id / fact_version，supersedes 必须指向同 issuer/metric 的较低版本。
- 新事件修订用新 accession / event_id / parent_event_id。
- 新行情/组合快照必须新 snapshot_id；相同 ID 对不同内容报 SNAPSHOT_CONFLICT。
- 配置发行时使用新 rule_version / calculation_version，保留旧代码版本和配置以支持旧计算重放；先跑真实 Golden，再 Shadow / Paper。
- 切换 AI 模式不升级规则，也不改变核心事实、状态或 sizing。

## 可观测性

- `/metrics`：机会状态计数、源健康、待复核队列、审计完整性。使用本地会话访问。
- `/api/v1/status`：来源错误、最近成功、发布阻断项。
- `/api/v1/audit`：最近 200 条审计，可核对完整哈希链。
- 日志使用结构化 JSON；HTTP 路径不作为访问日志输出，避免查询参数泄漏。
- 可选 SEC worker `jobs` 表保存每次执行状态和失败摘要。

外部告警投递、实时行情缺口告警、长期数据 SLA 和恢复演练仍属于生产发布门禁；没有声称已经完成。
