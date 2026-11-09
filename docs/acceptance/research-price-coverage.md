# 研究价格覆盖与缺口报告（T12）

状态：**软件已实现，真实价格轴未通过（awaiting_user_import）**。本报告不声称任何真实价格已核验。

## 1. 软件结论

| 项 | 结论 | 证据 |
|---|---|---|
| 逐证券价格规则（D 日、正值、USD、常规收盘、拆股基准、原件哈希/定位） | 通过 | `tests/adapters/test_price_file.py::test_row_rules`（11 条参数化） |
| 盘后价/旧价/持仓反推价/只叫 close 的值不作为正式价格 | 通过 | 同上 `NOT_REGULAR_CLOSE / STALE_PRICE / DERIVED_PRICE / PRICE_TYPE_UNDEFINED` |
| 全名单矩阵（非只验证单只） | 通过 | `test_matrix_covers_whole_universe_not_just_one_name` |
| 缺失/停牌/身份变更/拆股不明分别有原因 | 通过 | `test_explicit_status_rows_suspended_identity_split` |
| 不以旧价填缺 | 通过 | `test_no_stale_fill` |
| 完整名单未知时不输出覆盖百分数 | 通过 | `test_coverage_none_when_universe_incomplete` |
| 缺文件 → `awaiting_user_import` 并列出缺字段与证券 | 通过 | `test_missing_file_awaiting_user_import` |
| 无凭证 → `awaiting_credentials`，不发网络请求 | 通过 | `test_awaiting_credentials_no_network` |
| Alpaca 须 SIP/raw、Massive 须 adjusted=false，不自动以 IEX 代替 | 离线契约通过 | `test_vendor_contracts_offline`（**不代表供应商实接通过**） |

## 2. 真实数据结论

实施时 `DATA_ROOT` 与项目目录内没有用户提供的真实价格文件，也没有任何供应商凭证。因此：

- 真实价格覆盖：**未验证**（`awaiting_user_import`）。
- 研究页对应显示具体缺口（完整篮子权重、有效收盘价、逐证券 TTM 盈利尚未导入）。
- 完整真实价格轴保持**未通过**；此任务按计划以“软件＋真实缺口报告”完成。

## 3. 缺失输入清单（供用户补充）

价格文件为 UTF-8 CSV，每证券至少一行，列：

```
security_id,date,close,currency,price_type,session,adjustment,feed,split_basis_date,fetched_at,evidence_sha256,locator,status
```

要求：`date` 等于价格日 D；`price_type=regular_close`、`session=regular`；`currency=USD`；`adjustment=raw` 且给出 `split_basis_date`；`feed` 为 `sip`/`consolidated`/`official_close`；`evidence_sha256` 为原件 SHA-256，`locator` 指向原件页/表/行。停牌、身份变更、拆股不明用 `status` 显式标注。缺哪些证券以 CLI 矩阵为准。

核验命令（缺文件时输出 `awaiting_user_import`）：

```bash
ndx-pe check-prices --input RESEARCH_INPUT.json --prices PRICES.csv --basket-date YYYY-MM-DD --price-date YYYY-MM-DD
```

## 4. 后续

认证供应商实接（Alpaca SIP/raw、Massive adjusted=false）、连续 5 个交易日的严格窗口验证见 E01，不属首版关键路径。
