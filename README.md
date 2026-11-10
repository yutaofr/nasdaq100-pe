# 纳指100估值看板（本机个人使用）

零数据采购预算、只绑定 `127.0.0.1` 的中文估值看板：
- **自主计算估值（首页 `#/`）**：按 SRD §3 将各证券权重乘以盈利收益率后求和，再取倒数计算组合 PE。TTM 使用已报告 GAAP 盈利（优先四个已报告单季 EPS 之和；缺单季值时用已报告归母净利润 ÷ 稀释股数 × 股价，方法版本 2，见 `docs/ADD.md` §5.3），FY1 使用下一财年 normalized 一致预期；负盈利保留，缺失不填零。数据不完整时显示覆盖与缺口；覆盖权重 ≥90% 时显示“已覆盖部分 PE”并标明覆盖率，否则留空。完整 PE 只在全部齐备时显示。
- **外部估值对照（`#/reference`）**：单独展示来源公布的滚动 PE / Forward PE，附来源、原名、日期、口径限制与原件哈希；这些数字不作为首页自算 PE 的替代。

`#/research` 保留为自算首页的兼容入口。2026-11-09 用户纠正了 2026-11-08 ADD 中“引用指标作为首页”的降级策略；ADD 保留原决策供追溯，以本次纠正为准。

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

### 1. 外部估值对照（`#/reference`）
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

### 2. 自主计算估值（首页 `#/`）
```bash
ndx-pe validate --input research.json                                     # 结构/语义/覆盖报告，不发布
ndx-pe import --file research.json --basket-date 2026-11-06 --price-date 2026-11-06   # 归档并生成不可变快照
ndx-pe recompute --snapshot SNAPSHOT_ID                                   # 固定归档输入复算，identical=true 才一致
ndx-pe export --snapshot SNAPSHOT_ID --scope local --output OUT_DIR       # 复算包 JSON + CSV + metadata
ndx-pe build-local --snapshot SNAPSHOT_ID                                 # 研究发布，与引用发布互相隔离
ndx-pe check-prices --input research.json --prices prices.csv --basket-date … --price-date …
```
研究输入格式见 `tests/research_fixtures.py`（最小可用样例）与 `docs/ADD.md` §4。默认模式 `research/current/subset/weekly`；`--profile strict` 只允许 `current/full/daily`。

### 2a. 用已归档证据批量生成真实输入（方法版本 2）
```bash
python scripts/collect_nocp.py --input BASKET.json --evidence EVIDENCE_DIR --target-date D --index OUT/nocp-index.json   # 联网：每只证券一次 Nasdaq 官方收盘价；接口只回最近 5 个交易日
python scripts/build_research_v2.py --base-input BASKET.json --nocp-index OUT/nocp-index.json --store $NDX_PE_DATA_ROOT \
    --price-date D --observed-at T --output OUT        # 离线：读 SEC 缓存，写 research-input-v2.json 与逐证券 coverage-report-v2.csv
```
没通过核对的证券不会生成盈利行，原因写在 `coverage-report-v2.csv`；人工裁定不纳入的用 `--exclude 'TICKER=原因'`。

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
