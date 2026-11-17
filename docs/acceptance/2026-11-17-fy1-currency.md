# 2026-11-17 FY1 币种缺口修复

## 结果与未完成项

针对本机 D=2026-11-13 的归档批次，FY1 盈利行从 97 增至 99；实际进入估值为 98/101，DASH 仍无价格。四家的币种交叉核对已接入，只有 ASML、PDD 的完整 FY1 缺口关闭。CCEP、FER 在通过币种检查后暴露出独立的会计口径缺口，仍不生成盈利行。

| 证券 | 原始 Dec 2026 EPS | 原始 Dec 2027 EPS（FY1） | 核对币种/单位 | 构建结果 |
|---|---:|---:|---|---|
| ASML | 46.51 | 62.48 | USD / 纽约上市登记股 | ok |
| PDD | 10.03 | 12.02 | USD / 上市 ADS | ok |
| CCEP | 4.96 | 5.45 | USD / 上市普通股 | FORECAST_BASIS_UNVERIFIED |
| FER | 1.01 | 1.10 | USD / 上市普通股 | FORECAST_BASIS_UNVERIFIED |

CCEP、FER 的归档 surprise 响应都是 `data:null`、业务代码 1002（No record found）。删除币种限制不会解决这个问题。未将历史数据缺失当作 normalized 口径的证明，也未把其他供应商的口径声明套用到 Nasdaq 接口。

## 证据及强度

本次核对了 MarketBeat 的 [ASML](https://www.marketbeat.com/stocks/NASDAQ/ASML/earnings/)、[PDD](https://www.marketbeat.com/stocks/NASDAQ/PDD/earnings/)、[CCEP](https://www.marketbeat.com/stocks/NASDAQ/CCEP/)、[FER](https://www.marketbeat.com/stocks/NASDAQ/FER/earnings/) 页面。它们分别把两年预测标为美元每股，两个值都与对应 Nasdaq 归档值一致。证券标题/交易所映射用于确认是相同上市证券；PDD 不乘以普通股/ADS 比率。

这是跨页面数值匹配后的币种推断，**不是 Nasdaq 提供的币种字段、供应商书面确认或独立经济验收**。另一页面可能共用上游来源，不能据此声称独立验证了预测准确性。观察记录为浏览工具返回文本的人工事实摘录，不是原始 HTML；证据目录明确标注这一点。直接抓取 Nasdaq、MarketBeat 和 Zacks 页面遇 403 后未重试或绕过；没有以其他数据集的 FAQ 代替本接口契约。

可复核记录在 `evidence/2026-11-17-fy1-currency/`，副本放在本机 `~/ndx-pe-data/inputs/evidence/fy1-currency/`。索引包含预测响应哈希、FY1 期末、EPS、审核时间、证据文件哈希及股类说明。构建器校验这些绑定；响应改变或证据不可读时关闭补证路径。盈利获取时间仍保留原始 2026-11-16 UTC 时间，没有用审核时间刷新旧预测。ASML、PDD 保留 `BASIS_COMPARISON_UNAVAILABLE` 和 `FORECAST_FRESHNESS_UNVERIFIED`，新增 `FORECAST_CURRENCY_CROSSCHECKED`。

## 验证与本机输出

- 先观察到两个回归测试失败，再实现修复；新增测试覆盖非美元报表的正向进入内核、币种/单位/证券/期间/数值/时间/哈希错误、路径越界，以及不能绕过缺失会计口径。
- 全量 pytest：374 passed，1 skipped。未修改前端；本次未重跑浏览器端测试。
- 本机归档输入重新构建、validate 和 import 成功；recompute 返回 `identical=true`。
- 输出：`~/ndx-pe-data/inputs/research-2026-11-13-fy1-currency-review/`。
- 快照：`193c9df0d8f5f9e9a757`；本机发布：`f82f8a4f1487e278`。
- 本批次 FY1 有效权重 99.2365%，已覆盖部分 PE 17.7817；完整 FY1 PE 仍为空。该结果只适用于归档篮子与本次观察截点，不是 11 月 17 日的新市场快照。

后续 CCEP、FER 需要能直接绑定该预测序列的会计口径说明，或另一套期间、币种、normalized 均值、上市股类及新鲜度均通过验证的完整预测输入；不可仅修改状态为 ok。
