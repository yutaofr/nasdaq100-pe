# TTM 补证核验记录（T13）

执行时间：2026-11-09（UTC 08:01–08:02）。**结论：软件通过；完整真实 TTM 未完成（本轮 3 个样本发行人均无合格 TTM）。**

## 1. 本轮真实核验

方式：`SecClient`（User-Agent 为通用标识、无联系邮箱——若 SEC 日后要求联系方式，请在 `config` 中配置；最小请求间隔 0.15s；失败最多退避重试 2 次）依次读取 3 个发行人的 `companyfacts`，每个 1 次请求，日志只含主机与状态。归档在 `~/ndx-pe-data/store/{raw,sec_cache}`。

| 发行人 | CIK | checked_at (UTC) | 原件 SHA-256 前缀 | 自动结论 |
|---|---|---|---|---|
| AAPL | 0000320193 | 2026-11-09T08:01:36Z | `f085735b4d08fb11` | `missing_quarter`（缺 Q4） |
| MRNA | 0001682852 | 2026-11-09T08:01:37Z | `bd7e019c7861dc64` | `missing_quarter`（缺 Q4） |
| COST | 0000909832 | 2026-11-09T08:01:38Z | `b675ced201b27ede` | `missing_quarter`（缺 Q4，16 周季） |

共同原因：SEC `companyfacts` 对第四季度只给全年值，不给单季稀释 EPS。例如 AAPL 最近已报告单季为 2025-09-28→2025-12-27（2.84）、2025-12-28→2026-03-28（2.01）、2026-03-29→2026-06-27（2.02），其前一季 2025-06-29→2025-09-27 不存在，故最近四个连续季度凑不齐；MRNA 缺 2025-10-01→2025-12-31，COST 缺 2025-05-12→2025-08-31。系统**按政策不用“全年−九个月”差分补 Q4**，三家全部进入补证队列（类别 `MISSING_Q4`，需 8-K/业绩公告中明确的单季 EPS 及页/表定位）。

## 2. 核验中发现并修复的真实缺陷

首次真实运行时 COST 的同一标签同时含 `pure`（2010 年旧值）与 `USD/shares` 两个单位，旧实现取第一个单位，得到 2010 年的“TTM 2.92 / currency=pure”。修复：只接受 `…/shares` 单位，优先 `USD/shares`；回归测试 `test_per_share_unit_preferred_over_pure_unit`、`test_non_per_share_only_unit_is_missing_label`（先红后绿）。如果没有真实核验，这个错误只会被合成夹具漏掉。

## 3. 软件验收对照

| 计划标准 | 证据 |
|---|---|
| 四个连续已报告单季 GAAP 稀释 EPS 之和，保存 `reported_quarter_eps_sum` 与逐季定位 | `test_ttm_is_sum_of_four_reported_consecutive_quarters` |
| 合法 16 周季通过；Q4 不用差分补；四季和与全年差异保留；不确定转人工 | `test_legal_16_week_quarter_accepted`、`test_missing_q4_not_derived_from_annual_minus_nine_months`、`test_annual_difference_recorded_not_forced`、`test_auto_parse_uncertain_goes_manual_review` |
| MRNA 负值、GOOG/GOOGL 股类、ASML 币种、拆股基准、ADR 单位未明 | `tests/validate/test_earnings.py` 对应用例 |
| `checked_at` 仅在实际成功查询后更新；离线重读不刷新；复核失败不冒充最新；新披露产生新版本 | `test_unchanged_content_updates_checked_at_only`、`test_offline_reread_does_not_refresh`、`test_failed_check_does_not_masquerade_as_latest`、`test_new_disclosure_new_version_and_gap_task` |
| 缺口队列先分类再按权重，低权重不删除 | `test_gap_queue_classified_then_weight_ordered_low_weight_kept` |
| FY1 证据（期间、财年末、mean、normalized、币种）；forwardPE 不能代替 | `test_fy1_*` 系列 |
| 速率上限、退避、UA、401/429 不无限重试、日志不泄露 | `test_429_limited_retries_with_backoff`、`test_401_not_retried`、`test_min_interval_between_requests`、`test_logs_never_contain_response_or_secret` |

## 4. 未完成与后续

- 完整真实 TTM：**未完成**（样本全部缺 Q4；101 只篮子更未核验）。不影响首版放行。
- 人工补录入口已实现：`ndx-pe import-supplement --file S.json --evidence-dir DIR`（每条须带 issuer_id、起止日、eps、currency、form、filed、原件 SHA-256、页/表定位、reviewed_at；原件哈希核验失败整批不写入）。补录只参与季度连续性判断，标记 `manual=true` 并随 TTM 保留原件哈希与定位；与 SEC 同期值冲突转人工复核（`MANUAL_CONFLICT`），币种不符不混用。`ndx-pe ttm-report --issuer cik-…` 离线复核。证据：`tests/adapters/test_supplements.py`。**本机尚未录入任何真实补录**，AAPL/MRNA/COST 仍缺 Q4，需你从 8-K/业绩公告取得单季值与原件。
- FY1：只实现了证据校验，未接入任何 FY1 数据源（E03）。
