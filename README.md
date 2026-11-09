# 纳指100估值看板（本机个人使用）

零数据采购预算、只绑定 `127.0.0.1` 的中文估值看板：
- **整体估值参考**：展示来源公布的滚动 PE / Forward PE，附来源、原名、数据日期、观察时间、口径限制与原件哈希；
- **自主计算研究**（观察时点研究）：完整篮子 + 有效价格 + 逐步补齐的 TTM，显示覆盖率、缺失清单与公式；缺数据时说明具体缺口，不用合成数值冒充。

设计与验收见 `docs/ADD.md`、`docs/superpowers/plans/…`、`docs/acceptance/release-v1.md`。

## 安装（锁文件可重现）

```bash
uv sync --extra dev                       # 依据 uv.lock 安装 Python 依赖到 .venv
npm --prefix apps/web ci                  # 依据 package-lock.json 安装前端依赖
npm --prefix apps/web run build           # 产出 apps/web/dist
export NDX_PE_DATA_ROOT=~/ndx-pe-data/store   # 数据根目录，必须在代码/服务目录之外
```

之后用 `.venv/bin/ndx-pe …`（或 `PYTHONPATH=src .venv/bin/python -m nasdaq100_pe.cli …`）。

## 日常操作

### 1. 引用指标（首页）
1. 手工取得来源原件（PDF/HTML），放进一个证据目录；计算其 SHA-256。
2. 写 JSON 输入（字段见 `schemas/published-observation.schema.json`）：`source_as_of` 页面未注明就填 `null`，口径未知填 `unknown`，不要从名称推断。
3. 校验 / 归档 / 构建 / 打开 / 导出：
```bash
ndx-pe import-published --file in.json --validate-only
ndx-pe import-published --file in.json --evidence-dir EVIDENCE_DIR        # 返回 batch_id
ndx-pe build-local --observations BATCH_ID                                 # 经本机 HTTP 校验后才切换指针
ndx-pe serve --port 8765 --web-root apps/web/dist                         # 浏览器打开 http://127.0.0.1:8765
ndx-pe export --observations BATCH_ID --scope local --output OUT_DIR
```
4. **周度检查**：每周对来源核对一次，保存新证据并记录：
```bash
ndx-pe check-published --series 'SERIES_KEY' --evidence NEW_FILE --evidence-dir EVIDENCE_DIR
ndx-pe build-local
```
页面据最后一次“有证据的检查”+7 天判断“周度检查逾期”；单纯刷新页面不会改变检查时间。库内同时有真实与演示数据时，`build-local` 需 `--data-mode real|synthetic`。

### 2. 自主计算研究
```bash
ndx-pe validate --input research.json                                     # 结构/语义/覆盖报告，不发布
ndx-pe import --file research.json --basket-date 2026-11-06 --price-date 2026-11-06   # 归档并生成不可变快照
ndx-pe recompute --snapshot SNAPSHOT_ID                                   # 固定归档输入复算，identical=true 才一致
ndx-pe export --snapshot SNAPSHOT_ID --scope local --output OUT_DIR       # 复算包 JSON + CSV + metadata
ndx-pe build-local --snapshot SNAPSHOT_ID                                 # 研究发布，与引用发布互相隔离
ndx-pe check-prices --input research.json --prices prices.csv --basket-date … --price-date …
```
研究输入格式见 `tests/research_fixtures.py`（最小可用样例）与 `docs/ADD.md` §4。默认模式 `research/current/subset/weekly`；`--profile strict` 只允许 `current/full/daily`。

### 2b. TTM 缺 Q4 时人工补录
SEC companyfacts 不给 Q4 单季 EPS，TTM 会显示 `missing_quarter`。从 8-K/业绩公告取得该季“已报告”稀释 EPS（禁止用全年−九个月推算），保存原件，写补录 JSON：
```json
{"schema_version":"1","supplements":[{"issuer_id":"cik-0000320193","start":"2025-06-29","end":"2025-09-27","eps":"1.85","currency":"USD","form":"8-K","filed":"2025-10-30","evidence_sha256":"<原件SHA-256>","locator":"Ex.99.1 第3页 表2","reviewed_at":"2026-11-09T00:00:00+00:00"}]}
```
```bash
ndx-pe import-supplement --file supplement.json --evidence-dir EVIDENCE_DIR
ndx-pe ttm-report --issuer cik-0000320193        # 离线读取SEC缓存+补录，看是否凑齐四个连续季度
```

### 3. 状态、备份与恢复
```bash
ndx-pe status                                   # 导入/归档/发布/备份状态；退出码 0 不代表数据完整
ndx-pe backup --dest ~/ndx-pe-data/backups/YYYYMMDD
ndx-pe restore --source ~/ndx-pe-data/backups/YYYYMMDD --target ~/ndx-pe-data/restored   # 目标须为空；自动重建索引
ndx-pe recompute --snapshot SNAPSHOT_ID         # 恢复后复算核对
```
未做备份时 `status` 显示“未配置备份，无恢复保障”。备份仅本地，**没有异地备份**；每日自动备份属 E04。

### 交易日历
内置 `src/nasdaq100_pe/config/calendar_us_2026.json`（止于 2026-12-31）。进入 2027 年前，请按交易所公告核对后新增 `calendar_us_2027.json`（格式同 2026 文件）；日历未覆盖的日期一律拒绝，不做猜测。

## 退出码
`0` 完成（可含部分数据，以 JSON 的 `completeness` / `publication_status` 为准）；`2` 输入或配置错误；`4` 整批质量校验失败（如无完整篮子）；`6` 存储或发布错误；`3` 采集失败、`5` 公开权限阻止——预留，首版未使用。

## 一键验收
```bash
scripts/verify-local.sh                         # 后端测试 → 前端单测 → 构建 → 浏览器 E2E
npm --prefix apps/web run test:perf             # 约110条合成证券的 LCP/传输量，结果写入 docs/acceptance/perf-results.json
```
E2E 用系统已安装的 Chrome（Playwright `channel: "chrome"`），不额外下载浏览器。

## 安全边界
只绑定 `127.0.0.1`，只读（无上传/配置接口），不开放 CORS，Host 白名单；DATA_ROOT 在服务目录之外；原件、完整异常栈、路径、令牌不进入发布包；导入不会访问任何导入字段里的 URL。**公网发布不在首版范围（E05）**。
