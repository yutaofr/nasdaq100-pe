# 首版验收报告（T14）

日期：2026-11-09。本报告把“软件”与“真实数据”结论分开写；**不把设计定稿、探针通过或退出码 0 写成产品/数据全部通过**。旧验证报告保持原判定，未改动。

## 1. 分项结论（ADD §0.5 / 计划 T14）

| 验收项 | 结论 | 依据 / 影响 / 后续 |
|---|---|---|
| 真实引用数据 | **通过** | 滚动 PE `25.85`、Forward PE `19.31`（Stock Analysis，2026-11-09 08:00Z），原件哈希与定位可回查，口径 unknown，数据日期未注明；`docs/acceptance/published-real-data.md`。**限制**：Invesco factsheet 被源站 406 拒绝（blocked，未绕过）；未做真实断网对照。 |
| 本机软件 | **通过** | 引用导入/校验/页面/导出/历史/错误与空状态、回环与秘密保护均有自动化证据（§2）。 |
| 本机部署 | **通过（手动 serve）** | 手动 `serve` 满足首版；**未安装 launchd**（属 E04，未验）。 |
| 研究功能 | **软件通过；真实研究输入缺口** | 公式/负值/缺失/子集/模式隔离测试通过；本机无真实完整篮子、价格、盈利输入，页面显示具体缺口，不显示合成数值。 |
| 完整真实 TTM | **未完成** | 3 个真实样本全部缺 Q4（`docs/acceptance/ttm-evidence.md`）。影响：自算 TTM 无合格真实点。后续 E02，并“人工补录单季 EPS”入口已补（见 ttm-evidence.md §4），待录入真实补录。 |
| 完整真实 FY1 | **未完成** | 只做了证据校验，无数据源。后续 E03。引用 Forward PE 卡片不受影响。 |
| 无人值守 | **未验** | E04。 |
| 公网发布 | **不适用** | E05，首版不涉及。 |
| 真实价格轴 | **未通过**（`awaiting_user_import`） | `docs/acceptance/research-price-coverage.md`。 |

## 2. 测试与证据（本次最终运行）

| 套件 | 结果 |
|---|---|
| `pytest tests` | 280 通过、1 跳过（含补录入口 14 条）；下方 §5 为补录前的完整脚本运行（`localhost` 绑定用例：策略固定为字面量 127.0.0.1） |
| `vitest --run` | 36 通过（引用页 16、研究页 20） |
| `playwright test`（系统 Chrome） | 28 通过：引用页、研究页、四视口、键盘、只读/Host/穿越、无第三方请求 |
| 性能 `test:perf` | 见 §3 |

计划 Review Focus 五项落点：
1. 网页报价日期不当 PE 日期：`test_quote_date_not_metric_date`、真实闭环中 `source_as_of=null`。
2. 周日读周五价：`test_sunday_research_reading_friday_price_ok_and_strict_rejects`。
3. 覆盖率与完整性独立：`test_missing_member_blocks_complete_even_if_coverage_rounds_to_100`、`test_zero_weight_missing_also_blocks_complete`、UI “完整权重未知”。
4. `content_fetched_at` 与 `checked_at` 分离：`test_unchanged_content_updates_checked_at_only`、`test_failed_check_does_not_masquerade_as_latest`。
5. 迟到请求/旧修订不回退：前端 `慢请求A在快请求B后返回…`、`test_late_revision_cannot_replace_current`、`test_late_old_revision_cannot_replace_new_release`。

## 3. 性能（合成约 110 条，`docs/acceptance/perf-results.json`）

Chrome 156.0.8078.80；390×844；冷缓存；CPU 4×降速；10Mbps 下行/1Mbps 上行/100ms RTT；5 次。LCP 中位数 612 ms、最差 640 ms（限值 3000 ms）；压缩后传输最差 68.6 KiB（限值 500 KiB）。
**说明**：数据为合成演示；服务端对 JSON/JS/CSS gzip；研究发布只含被选择的快照，首屏只请求该发布的文件；LCP 候选可能是页头/首个大块文本，这项指标说明首屏可见速度，不等于表格交互就绪时间。

## 4. 已知限制与偏差（均已在账本记录）

- 项目目录不是 Git 仓库，计划禁止初始化 Git：**没有任何提交**；变更记录在 `.superpowers/progress.md`（git 忽略）。
- 第 7 项 `test_identity.py`、`fixtures/synthetic/formula-cases.json` 的内容并入 `test_basket.py` / `test_core.py`。
- 策略：研究发布与引用发布使用独立指针；引用发布若“丢失已有序列或回退序列水位”会被 `STALE_REVISION` 拒绝（需显式回滚，留审计）。
- 前端历史“交易日缺口”只按工作日判断，节假日会被误判为缺口（日历仅在后端）。
- 本轮没有用独立审阅者：见 §6。

## 5. 最终运行

`scripts/verify-local.sh` 最后一次输出（2026-11-09）：backend 266 passed / 1 skipped；web unit 36 passed；build ok；e2e 28 passed；`ALL CHECKS PASSED`。

## 6. 独立评审（提交 2e18e89，Opus 评审者，只读）

结论：无 Critical，8 条 Important，已在同一轮全部修复（每条先写失败测试，见 `tests/test_review_fixes.py`；修复后后端 294 通过/1 跳过，前端 37，E2E 28）：
1. 篮子日 W 必须等于 `weights.date` / `universe.as_of`（含 strict）；2. 更正后的原值不再当最新，历史标“已更正”；3. 观察时间与 T 统一 UTC；4. 研究路径强制 USD / 常规收盘，真实模式要求价格证据；5. 备份包含 `supplements/`；6. 财报新鲜度看 `checked_at`，`fetched_at` 仅作出处；7. 研究发布按“并入当前发布”累积，修订比较取每键最大值；8. D 必须是交易日、未知日历拒绝，日历按 `config/calendar_us_YYYY.json` 多文件合并（**现有日历止于 2026-12-31，2027 年需核对交易所公告后新增文件**）。

延后的 Minor（未改）：`build-local` 的 CAS 期望值在构建后才读取；引用发布水位未含 `checks.json`；`--web-root` 未强制不含 DATA_ROOT；密钥扫描漏 JSON 形式 `"api_key": "x"` 且用未 resolve 的路径；SEC 缓存元数据非原子写；无 `fetch_earnings` CLI；重复价格/盈利行第三条会被重新放入；研究历史按 T 而非 D 排序且被取代的修订仍画点；总市值恒不可用（未接入）；缺 `data_mode` 的研究输入默认标合成；导入/研究运行无写锁。

## 7. 评审方式（此前）

本轮在单一会话内按任务逐个 TDD 实施，没有派发独立评审者；§2 的变异检查（人为破坏规则、确认测试变红）覆盖了篮子校验、计算内核与资格边界，但**这不等同于第二双眼睛**。合并/交付前建议另行评审，重点：发布指针 CAS 与回退判定（`publisher/pointer.py`）、资格边界（`validate/eligibility.py`）、SEC 季度选择（`normalize/quarters.py`）。

另：`schemas/` 通过向上查找仓库目录定位，适用于本仓库的可编辑安装；若改为打包成 wheel 需把 schemas 打进包。
