# 真实引用数据验收（T06，M1 关卡）

执行时间：2026-11-09（UTC 08:00–08:02）。结论分开记录：**真实数据结论：通过（条件见 §4）；软件结论：通过。**

## 1. 来源与原件

| 来源 | 结果 | 说明 |
|---|---|---|
| Stock Analysis `https://stockanalysis.com/etf/qqq/` | 已取得 HTML 原件（157,531 字节） | 本机路径 `~/ndx-pe-data/inputs/evidence/stockanalysis_qqq.html`，SHA-256 `14f3a4df209e44f3ca880a01b5e7a58cbcbbcdcb79ba26c9b2ce580c5a277813`，获取时间 2026-11-09T08:00:28Z |
| Invesco QQQ factsheet PDF | **blocked** | 服务器对自动化请求返回 HTTP 406，得到 0 字节文件。已删除该空文件，**未用伪装请求头重试**（不绕过来源的自动化访问限制）。需要时请手动下载 PDF 放入证据目录后按 `import-published` 导入。 |

## 2. 核对记录（原件 → 输入 → 页面/导出）

| 指标 | 原名 | 值 | 原件定位 | 数据日期 | 观察时间 |
|---|---|---|---|---|---|
| 滚动 PE（`trailing_pe`） | `PE Ratio` | `25.85` | 统计表行“PE Ratio”；页面内嵌数据 `peRatio:"25.85"` | **来源未注明**（`null`） | 2026-11-09T08:00:28Z |
| Forward PE（`forward_pe`） | `Forward PE` | `19.31` | 统计表行“Forward PE”；页面内嵌数据 `peForward:"19.31"` | **来源未注明**（`null`） | 2026-11-09T08:00:28Z |

- 同一页面另有“持仓表 updated: Nov 6, 2026”，那是持仓日期，**未**被当作 PE 数据日期（对应 `test_quote_date_not_metric_date`）。
- 期间、会计口径、亏损处理、方法披露均为 `unknown`：来源页面未说明；二者不要求同口径。
- **归类说明**：把“PE Ratio”归入滚动 PE 是 ADD §0.1 对该来源的归类；页面本身未写明 TTM。该判断已体现在 `period_basis=unknown`，页面显示“来源未披露（未知）”。

## 3. 正式 CLI 闭环（数据根 `~/ndx-pe-data/store`）

| 步骤 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 导入+归档 | `ndx-pe import-published --file published_real_2026-11-09.json --evidence-dir …/evidence` | 0 | batch `66f1c279db6e10dfa435aced59135720`，2 条观察，原件哈希校验通过 |
| 构建+HTTP 校验+提升 | `ndx-pe build-local --observations 66f1c279…` | 0 | release `34f3fd1c81aadc38` |
| 导出 | `ndx-pe export --observations 66f1c279… --scope local --output ~/ndx-pe-data/exports/published-20261109` | 0 | `published.json` / `published.csv` / `metadata.json` |
| 状态 | `ndx-pe status` | 0 | 2 观察已索引；`current_release=34f3fd1c81aadc38` |
| 服务 | `ndx-pe serve --port 8790 --web-root apps/web/dist` | — | `/healthz` 返回 `ok`，`empty=false` |

页面（浏览器实测）显示：滚动 PE `25.85 倍`、Forward PE `19.31 倍`，数据日期均为“来源未注明，观察于 2026-11-09 08:00 UTC”，口径四项均“来源未披露（未知）”，页头为真实数据。页面、JSON、CSV 三处数值与日期一致；CSV `value` 列为数字、日期列为空。

## 4. 离线与隔离

- 页面加载的全部资源主机仅 `127.0.0.1:8790`（浏览器 `performance` 资源条目核验），因此浏览已发布内容不依赖外网。**我没有实际断开网络做对照**，此项为“依据请求清单的推断”。
- 数据模式为 `real`，没有合成占位值；演示数据与此库隔离（`MIXED_DATA_MODES` 拒绝混发布，见 `test_real_and_synthetic_isolated_in_input_history_release_export`）。

## 5. 结论

- 首版要求“至少一条真实滚动 PE、一条真实 Forward PE，可追溯到原件，未知口径明确标识”：**满足**（均来自 Stock Analysis 同一原件，允许同源）。
- 未完成/限制：Invesco factsheet 未取得（blocked）；二者的口径均未知；未做真实断网对照。
- 数值时效：页面值只代表 2026-11-09 08:00Z 的观察，不代表之后的数据；周度检查到期时间为观察/最近检查后 7 天。
