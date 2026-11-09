# 纳指100估值看板架构验证报告

- 核查日：2026-11-08（巴黎时间）
- 基线：[ADD v0.1 §12.2](ADD.md) 和 [SRD v0.3](SRD.md)
- 实测附件：[逐证券验证矩阵（CSV）](data-feasibility-matrix.csv)，仅作本地核查证据

## 验证结论

**零预算的完整真实估值和公开发布均未通过准入。** 官方同日权重未取得。Invesco 返回了完整的 QQQ 代理候选篮子，但日期滞后一交易日，且缺少排除事件的证据。SEC 探测覆盖代理篮子的全部 101 只证券；可批量获取的财务事实离完整 TTM 仍有差距，FY1 也缺少满足期间、会计口径及使用权限的全量来源。本轮未生成真实组合 PE 或可回填历史点。

| ADD §12.2 待验证事项 | 结果 | 当前处置 |
|---|---|---|
| 免费官方完整权重及日期 | 未通过。匿名 GIW 缺明细；QQQ 返回 D−1 权重 | 保留独立的 QQQ 代理候选；当日组合权重不可用 |
| FY1 期间、normalized 口径与覆盖 | 未通过。已找到单证券口径样例，未确认免费合规的全量日更 | 完整 FY1 不可用，保留明确的缺失原因 |
| TTM GAAP、负盈利、季度及拆股 | 部分验证。100 个 SEC 发行人响应成功；直接连续季度仅 1/101，另有人工补证样例 | SEC 作为财报事实候选；校验季度、股类和价格基准后才纳入 |
| 公司行动及成分事件 | 部分验证。交易日历和已知变更可核，未证明事件流完整 | 关闭 D−1 估算通道 |
| 公开显示、派生与下载 | 未通过。完整真实估值缺少来源授权链 | 公开包仅使用已获准字段或明确标识的合成数据 |
| 本地调度及免费托管 | 部分验证。真实系统触发和本地合成发布通过；账号额度和实际部署待验 | 保留本地调度，生产发布仍有独立验收条件 |
| 历史数据 | 未通过。零个可合规回填的估值点 | 两条历史序列从各自首个合格快照积累 |

### 实测口径

选 2026-11-06（周五、纽约时间）为目标交易日 D。ADD 的采集截止为纽约 11-07 12:00，即 17:00 UTC、巴黎 18:00。探测在 11-08 巴黎晚间执行，故本轮响应只能作能力证据。SEC 额外按 `filed ≤ D` 初筛，以便核对目标日前后可能存在的事实；正式历史校验仍须逐 accession 核对接收时间、实际公开可得时间及当时采集记录。

矩阵以 QQQ 11-05 响应中的全部股票和存托凭证为范围。它保存候选代码、发行人 CIK、SEC 响应哈希和获取时间、财报期间及 accession、候选值、价格和 FY1 的探测状态及资格判定。代码与 CIK 的当前匹配仅建立发行人关联，股类有效期和证券身份仍需验证。逐股权重留在本地原始响应，附件只给出存在标记，报告以聚合量呈现筛查结果。对目标日 D，**TTM 和 FY1 合格证券均为 0/101，正式有效权重覆盖率均为 `null`**。缺少合格 D 日权重分母，不能填 0%；下文的百分比仅按已观测的 D−1 代理篮子计算。

## 1. 权重和同日价格

- **官方权重。** 匿名请求 Nasdaq GIW 的 NDX Weighting 得到 HTTP 200，但证券表体为空，页面要求登录。官方手册说明登录后可按日期选择 End of Day、查看完整名单和权重。零预算可用的账户权益和自动接口未证实，故 D 日官方名单与权重无合格观测。[NDX 权重页](https://indexes.nasdaqomx.com/Index/Weighting/NDX) · [Nasdaq GIW 指南](https://indexes.nasdaqomx.com/docs/Tips%20to%20Navigate%20Your%20New%20Global%20Index%20Watch%20Access.pdf)
- **第三方列表。** Stock Analysis 的 Nasdaq-100 页面说明其名单和权重取自 QQQ，页面的 101 只证券可作代理范围的交叉参考，不能补证同日官方权重。[Stock Analysis 名单来源](https://stockanalysis.com/list/nasdaq-100-stocks/)
- **QQQ 代理。** 一次性核查 Invesco「All QQQ holdings」页面公开加载的数据。页面所用 `interval=monthly` 与单次对照 `interval=daily` 均为 HTTP 200，响应 SHA-256 相同，且 `effectiveDate` 和 `effectiveBusinessDate` 均为 2026-11-05。源计数与实际行数同为 106。股票集合为 98 普通股、3 存托凭证，101 个代码和 CUSIP 各自唯一，股票权重全部存在且非负。5 条排除项为现金、现金抵押、期货、抵消期货的合成现金和待付股息现金行；已披露的净排除权重为 0.168071%，另 1 条非股票权重为 `null`，保留缺失。股票权重和为 99.831932%，代理归一化因子约 1.00168350944，合计到 100%。两种参数结果相同，不能据此推定更新时间或连续日更能力。当前 D−1 事件覆盖门槛未满足。[Invesco QQQ 持仓页](https://www.invesco.com/qqq-etf/en/about.html) · [页面持仓端点](https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/fund?idType=ticker&interval=monthly&productType=ETF)
- **价格。** Yahoo Chart 单次 AAPL 探针返回 HTTP 200，含 D 日 USD 日线及非空 `quote.close`，交易所时区为纽约。未建立完整篮子覆盖、拆股基准、生产采集权限或截止前证据。条款核查后停止对该来源的批量自动探测。其余 100 只价格记为未测，目标日可用价格集仍缺失。[Yahoo Chart 样本](https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d)

## 2. FY1 期间、会计口径与覆盖

- Yahoo AAPL `quoteSummary` 单次请求得到 HTTP 401 `Invalid Crumb`；公开分析页的搜索索引可见 GAAP、Normalized、Current Year、Next Year，直接复核 AAPL 页面遇到 HTTP 429。Yahoo 页面有口径选择的迹象，无法把该选择绑定到候选 API 返回值。yfinance 的 `earnings_estimate` 公开表结构有 `+1y` 和 `avg`，还需原始期间结束日、字段级会计口径、币种及可持续授权。[Yahoo 分析页](https://finance.yahoo.com/quote/AAPL/analysis/) · [yfinance 接口实现](https://github.com/ranaroussi/yfinance/blob/main/yfinance/base.py)
- Stock Analysis 的 AAPL 页面同时显示当年和下一财年的预测，下一财年对应 FY2028、2028-09-30，并说明使用调整后 EPS。这个样本说明跨财年时不能按自然年或字段名推断 FY1。页面最后更新时间不能代替该条 EPS 的修订时间。观测在截止后，仅作口径参考。[AAPL 预测页](https://stockanalysis.com/stocks/aapl/forecast/)
- 101 行均无合格 FY1 来源记录。全量方案必须逐证券拿到下一财年结束日、分析师均值和 normalized 字段依据。有修订时间的记录按 30 天检查；缺时间的合格现值须带 `FORECAST_FRESHNESS_UNVERIFIED`。未知口径保留为无效输入。

### 备选 FY1 来源

- **Alpha Vantage**。官方 `EARNINGS_ESTIMATES` IBM demo 在本机返回 HTTP 200 和 42 条记录，其中年度预测有 `horizon=fiscal year`、财年结束日、EPS 均值与 7/30/60/90 天前均值字段。响应未提供 GAAP/normalized 字段或逐记录实际更新时间；相对回看字段不能证实任意历史日的观察截点。AAPL/MSFT 同一 demo 均为 HTTP 200 但只有 `Information`，无预测记录。标准免费配额 25 次/日，且每请求一代码；文档另列获验证的开源或教育项目例外，本项目资格未经证实。没有合格全量输入。[接口文档](https://www.alphavantage.co/documentation/#earnings-estimates) · [免费限额](https://www.alphavantage.co/support/)
- **Stock Analysis / S&P Global**。AAPL 页面可见明确的下一财年 EPS 及财年结束日，网站更新记录确认 forecast 页采用 non-GAAP adjusted EPS，数据来源页确认由 S&P Global 提供一致预期，可作单点口径对照。服务条款限制产品自动采集，官方帮助确认没有数据 API 或程序化转授权；本轮只做单页核查，未做批量获取。该来源未通过全量日更和许可门槛。[AAPL 样本](https://stockanalysis.com/stocks/aapl/forecast/) · [口径说明](https://stockanalysis.com/changelog/) · [数据源](https://stockanalysis.com/data-sources/) · [使用条款](https://stockanalysis.com/terms-of-use/) · [API 说明](https://stockanalysis.com/help/faq/api-access/)
- **Zacks Street EPS**。Nasdaq Data Link 文档明确年度期间及调整口径，数据产品标为 Premium。Zacks 公开媒体页列出全公司样表链接，本轮该链接返回访问挑战页，覆盖与自动使用权未得到验证。[Zacks 数据产品](https://data.nasdaq.com/databases/ZSEE) · [媒体样表](https://www.zacks.com/media-room/estimates/estimates.php)

## 3. TTM GAAP、负盈利、季度与拆股

以 SEC 的 `company_tickers.json` 匹配 101 只证券到 100 个 CIK。按每批最多 4 个、批次起点间隔至少 1.05 秒发起 `companyfacts` 请求，100/100 返回 HTTP 200，未观测到限流。GOOG 与 GOOGL 共享发行人 CIK，矩阵分别保留两只证券。97/101 响应有 US GAAP 稀释 EPS 标签，96/101 有 USD/股单位，92/101 在回看范围内至少有一条直接季度数据。AAPL 的 Yahoo 财务时序探针也返回 USD 季度字段，但未随单条结果提供完整季度边界、原申报定位和拆股证据。[SEC API 与字段说明](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [SEC 代码映射](https://www.sec.gov/files/company_tickers.json)

筛查路径使用 `us-gaap:EarningsPerShareDiluted` 的 USD/股事实，回看 550 天，季度长度 77–105 天。相同期末取不晚于 D 的最新申报并标注值冲突。要求最近季末距 D 不超过 180 天，且最新四条的边界首尾相接。它只筛选直接季度事实；已披露但仅存在于附表、原财报或 8-K 附件的季度可能落空。正式校验须另证这些是来源当时最新四季，并核对股类、存托凭证换算和拆股基准。

| 直接季度筛查结果 | 证券数 | D−1 代理股票权重 |
|---|---:|---:|
| 四条连续且在 180 天内，待核股类与拆股 | 1 | 0.3273% |
| 季度缺少或不连续 | 85 | 92.7812% |
| 最近期末超过 180 天 | 6 | 4.2023% |
| 无近期直接季度 | 4 | 1.0731% |
| 无 US GAAP 稀释 EPS 标签 | 4 | 1.0055% |
| 无 USD/股单位 | 1 | 0.6106% |

- **AAPL，第四季度缺口。** SEC 结构化季度筛查漏掉 FY2026 第四季。Apple 11-02 发布当季稀释 EPS 2.10 美元，10-K 报告截至 09-26 财年的稀释 EPS 8.98 美元，四个已披露单季合计为 8.97 美元。每股收益使用加权平均股数且有四舍五入，取已报告全年值和加总单季须记录为不同路径。[Apple Q4 披露](https://www.apple.com/newsroom/2026/11/apple-reports-fourth-quarter-results/) · [Apple 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/aapl-20260926.htm)
- **MRNA，负盈利。** SEC 候选行保留负号。用 8-K 附件补核 2025 Q4 的 −2.11，再与 2026 Q1、Q2、Q3 的 −3.40、−1.97、0.38 核对，四季合计 −7.10 美元/股。矩阵有 14 只证券至少一条直接季度 EPS 为负；这只是季度负值计数，不能当作负 TTM 数量。[Moderna Q4 8-K 附件](https://www.sec.gov/Archives/edgar/data/1682852/000168285226000015/exhibit9912025q4pressrelea.htm) · [Moderna 季度披露](https://investors.modernatx.com/quarterly-results)
- **范围与价格基准。** ASML 的 SEC 稀释 EPS 标签未返回 USD/股事实，不能直接除以美股 USD 价格。GOOG 与 GOOGL 的共同 CIK 不能独立证明各股类 EPS 匹配。AAPL 历史拆股正例见第 7 节。没有通过基准对齐的证券行继续保持无效。

## 4. 公司行动、成分事件与交易日历

**日历来源可用，事件全覆盖未通过。关闭 D−1 估算通道。**

| 核查 | 可复核证据 | 判定 |
|---|---|---|
| 预定休市与半日市 | 2026-11-26 感恩节休市，2026-11-27 和 2026-12-24 纽约时间 13:00 提前收盘。日历说明提前收盘另有交易所通知。按 ADD 三个槽位和 Python `ZoneInfo("America/New_York")` 复算，11-27 纽约时间为 14:30、16:00、19:00，折合 UTC 19:30、21:00、次日 00:00。正常 16:00 收盘的首槽在 10-30 为 21:30 UTC，11-02 为 22:30 UTC。此为来源和时间换算验证，临时休市接入及生产调度另验。[Nasdaq Trader 交易日历](https://nasdaqtrader.com/Trader.aspx?id=Calendar) | 日历候选通过文档与样例检查 |
| 预定与临时指数事件 | NDX 方法规定定期调整及特殊再平衡。正例一为 2026-06-22 开盘前五进五出；正例二为 2026-10-09 开盘前 MRNA 替换 WBD，该日期应拒绝 10-08 权重滞后估算。匿名打开 NDX Corporate Actions 页面只得到登录提示。GIW 指南要求结合 CAUFF 理解事件全貌；Nasdaq 产品页明确 GIW 仅含有限事件资料，更完整的预告属于 GIFFD。[NDX 方法](https://indexes.nasdaq.com/docs/Methodology_NDX.pdf) · [6 月调整](https://ir.nasdaq.com/node/110541) · [10 月替换](https://www.nasdaq.com/press-release/moderna-inc-join-nasdaq-100-indexr-beginning-october-9-2026-2026-10-02) · [事件页](https://indexes.nasdaq.com/Index/CorpActions/NDX) · [GIW 指南](https://indexes.nasdaq.com/docs/Tips%20to%20Navigate%20Your%20New%20Global%20Index%20Watch%20Access.pdf) · [数据产品](https://www.nasdaq.com/products/global-indexes/data) | 已验证正例，未取得可证明无事件的连续流 |
| 证券公司行动 | Nasdaq Daily List 产品页列出拆股、股息、退市、名称和代码变更及历史数据，访问为月度订阅。2026-11-05 公告提到 2027-06-30 前迁移至 Nasdaq Data Link 后将有部分免费公开字段，范围与上线实测待核查。Apple 官网的 2020 年 4 拆 1 可作为拆股正例。[Daily List](https://nasdaqtrader.com/Trader.aspx?id=DailyListPD) · [迁移公告](https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-26) · [Apple 事件日期](https://investor.apple.com/dividend-history/default.aspx) | 未验证零预算下覆盖目标日期全部证券的拆股、并购、分拆、代码与股类变更 |

解禁条件为同时取得完整指数事件和目标篮子全部证券事件的生效时点、来源可用区间、更新时间及完整性证据，并通过已知调整、已知拆股、无事件、缺文件、过期文件五类检查。对 QQQ 代理还需检查基金股票集合是否发生变更。网页搜索无结果、单一拆股接口空响应、指数公告页能打开，均不能证明指定区间内无事件。

## 5. 公开许可与本地处理

**判定：真实估值的公开发布门槛未通过。** 核查日为 2026-11-08。下表按 ADD §8 判断指定路径的使用权限。本轮未形成可长期复用的授权记录，每项在发布前复核。适用条款、端点或字段变更时重新核查。`denied` 表示所列路径的条款明确限制项目计划中的使用且本次未见例外授权，`unverified` 表示缺少字段或产品级依据，二者均阻止相应发布。

| 来源与适用字段 | `local_processing` | `public_display` | `public_derived_metrics` | `public_download` | 依据 |
|---|---|---|---|---|---|
| Nasdaq 公开站点，指数成分及权重 | `denied`，针对提取并用于分析软件的路径 | `denied` | `denied` | `denied` | 网站条款 §§2、6–7、11 对采集、分析软件开发、复制、发布及衍生用途要求许可。[Nasdaq 网站条款](https://www.nasdaq.com/legal) |
| Nasdaq GIW 授权接口，指数成分及权重 | `unverified` | `unverified` | `unverified` | `unverified` | 官方说明 GIW 提供订户数据和安全接口。需要项目实际订阅权益和相应协议，公开站点的阅读权限不作为接口凭据。[GIW 产品说明](https://www.nasdaq.com/products/global-indexes/data/giw) · [GIW 接入入口](https://indexes.nasdaq.com/Index/) |
| Invesco US QQQ 网站，基金持仓及权重 | `denied`，针对自行反复抓取、归档和派生处理 | `denied` | `denied` | `denied` | §§4、9–10 允许有限个人访问，限制下载、显示与分发网站内容、衍生使用和自动提取。§10 对 Invesco 普遍提供的工具设有例外，具体下载功能可用于何种留存和分析需看其附加条款。[Invesco US 网站条款](https://www.invesco.com/us/en/resources/terms-of-use.html) |
| Yahoo Finance，经 yfinance 获取的价格、财报和预测 | `denied`，针对未经许可的自动采集 | `unverified` | `unverified` | `unverified` | 通用条款 §2.4(9) 要求自动访问或采集事先取得明确许可，§2.4(10) 限制替代性数据产品。未找到本项目对具体 Finance 端点及上游字段的授权。yfinance 开源许可覆盖代码，项目文档将数据使用指向 Yahoo 条款。法国/欧盟法语可查的历史版本有同一自动访问限制，当前法语条款页面本次未能读取。[Yahoo 通用条款（美国）](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) · [Yahoo 法语条款历史版本](https://legal.yahoo.com/ie/fr/yahoo/terms/otos/previousversion-2026-01-02/index.html) · [Yahoo 开发者 API 条款](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) · [yfinance 文档](https://ranaroussi.github.io/yfinance/) |
| SEC EDGAR，公开申报中的财务事实与 QQQ 持仓字段 | `allowed`，按 Fair Access | `allowed`，限所列公开事实 | `allowed`，仅限获准输入 | `allowed`，限所列公开事实 | SEC 明确允许复用 EDGAR 公开申报内容及复制、再分发其公开信息。字段应带申报来源与 accession，排除标识、图片、第三方附带材料和任何受限混合字段。脚本标识 User-Agent，总请求不超过 10 次/秒，并尽量减少负载。[SEC 复用 FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions) · [SEC 网站传播政策](https://www.sec.gov/about/privacy-information#dissemination) · [SEC Fair Access](https://www.sec.gov/about/developer-resources) |

策略按字段来源和用途组合判定。含受限来源的组合 PE、收益率或贡献值都继承其发布阻塞。任何浏览器可获取的 JSON 都按公开披露处理，CSV 下载另查再分发权限。公开包可使用明确标识的合成数据或仅含已获准且满足用途条件的字段。本次许可核查未建立可支撑完整真实 PE 的权重、价格和盈利授权链。

可复用的 EDGAR 持仓例证为 QQQ NPORT-P（accession `0001067839-26-000030`），持仓报告日 2026-06-30，2026-08-28 09:26:52 被 EDGAR 接收。这条记录可核对季度末持仓，发布时差使其不能支持 ADD 的日更或当时采集截止。SEC 在 2025 年推迟了增加 Form N-PORT 披露频率的规则，大型基金组适用日期为 2027-11-17。 [QQQ 申报索引](https://www.sec.gov/Archives/edgar/data/1067839/000106783926000030/0001067839-26-000030-index.htm) · [SEC 生效时间延期规则](https://www.sec.gov/rules-regulations/2025/04/s7-26-22)

## 6. 本地调度稳定性与 Vercel 免费条件

**判定：本地调度和静态发布可行性部分验证。** macOS 27.0.1（26A434，arm64）的已登录 GUI 会话中，用独立的临时 launchd Agent 运行仅写时间戳的命令。两个 plist 均通过 `plutil -lint`。短间隔试验将 `StartInterval` 设为 3 秒，记录到 5 次执行，巴黎时间 2026-11-08 22:19:38、:41、:45、:48、:51，最后退出码为 0。分钟日历试验用 `StartCalendarInterval`，在巴黎时间 22:20:14 加载，22:21:05 读到 1 次执行，最后退出码为 0。两个 Agent 均已卸载并确认移除，临时文件已清理。此次验证覆盖机器唤醒状态下的系统触发。长期运行、休眠唤醒、退出登录、重启和真实采集恢复仍需验证。

本机 `man launchd.plist` 说明，`StartInterval` 在休眠或任务仍在运行时可能错过触发，`StartCalendarInterval` 在唤醒时合并多个错过的触发。因此可用每小时 00、15、30、45 分的 `StartCalendarInterval` 调用轻量 tick，由持久状态和纽约交易日历决定该跑哪个槽位及是否已过截止。休眠触发合并来自手册，现场未主动使机器休眠。Python 3.15.2 `zoneinfo` 样例验证了美欧夏令时不同步及半日市换算。纽约 2026-03-06 和 03-09 的常规收盘后 90 分钟分别落在巴黎当日 23:30 和 22:30。Nasdaq 2026-11-27 纽约时间 13:00 半日市收盘，对应三个采集槽位为巴黎 11-27 20:30、22:00、11-28 01:00，采集截止为纽约 11-28 12:00。[Apple 调度文档](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html)、[Nasdaq 交易日历](https://nasdaqtrader.com/Trader.aspx?id=Calendar)

**托管方案核查。** Vercel Hobby 适用于个人、非商业用途。公开文档列出每天最多 100 次部署、单次 CLI 上传上限 100 MB、6,000 构建执行分钟、100 GB Fast Data Transfer、最多 100 万 Edge Requests。额度属于平台公开计划，实际需查目标账号的套餐和剩余额度。本机 PATH 未找到 `vercel`，环境未检测到 `VERCEL_TOKEN`，项目未绑定 `.vercel/project.json`，检查的常用认证文件路径中未找到认证文件。本轮未获取账号级额度和项目保护配置。Vercel 官方 Vite 模板通过本机 HTTP 客户端返回首页 200（429 B）和 JS 模块 200（53,329 B）。[Hobby 计划](https://vercel.com/docs/plans/hobby)、[账号计划](https://vercel.com/docs/plans)、[部署限制](https://vercel.com/docs/limits)、[Vite 托管说明及官方示例](https://vercel.com/docs/frameworks/frontend/vite)

**发布试验。** 本机仅绑定 `127.0.0.1`，用三个带合成标识的静态发布包执行 HTTP 验证。初始上线、拒绝哈希错误并保留旧指针、提升新版本、旧 manifest 仍访问旧版本、回滚旧版本五项通过。Vercel 实际项目的上传、独立部署 URL 校验、生产域切换、CDN 一致性和回滚待验证。实施时可用 `vercel deploy --prebuilt --prod --skip-domain` 先上传已过滤产物并验证，再用 `vercel promote` 切换。Hobby 内建即时回滚只支持上一个生产版本，仍须保留可重发的旧发布包。匿名 `--temporary` 以 production 为目标，本轮未上传或创建公开部署。[Vercel CLI deploy](https://vercel.com/docs/cli/deploy)、[域名切换](https://vercel.com/docs/cli/alias)、[即时回滚](https://vercel.com/docs/instant-rollback)

Vercel 旧版 Cron Jobs 在 Hobby 每项每日最多一次并按小时窗口触发。2026-11-05 发布公测的新版 Schedules 为不同功能，Hobby 支持每 15 分钟一次、触发抖动窗口 15 分钟、每账期 5,000 次运行，目标 Function 或 Queue 另计用量。它是后续云端候选，首版仍按 ADD 采用本地调度，超窗显示逾期并按政策恢复。[旧版 Cron 限制](https://vercel.com/docs/schedules/cron-jobs/usage-and-pricing)、[Schedules 公测公告](https://vercel.com/changelog/vercel-schedules-is-now-in-public-beta)、[新版 Schedules 限制](https://vercel.com/docs/schedules/limits)

## 7. 历史数据可得性

**零个历史点达到回填门槛。TTM 和 FY1 分开积累。**

| 所需输入 | 可取得证据与限制 |
|---|---|
| 当日成分和权重 | 匿名 NDX Weighting 页面有日期和列头但无证券明细，要求登录。GIW 指南说明登录后按日期选收盘权重。QQQ 在 EDGAR 有历史 NPORT-P 样例，报告期为 2026-06-30，2026-08-28 09:26:52 才被接收，超过报告日次日纽约 12:00 截点；此记录可核对月末持仓，不能作为当日已获取的完整快照证据。指数点位序列只可验证指数点位。[NDX Weighting](https://indexes.nasdaq.com/Index/Weighting/NDX) · [GIW 指南](https://indexes.nasdaq.com/docs/Tips%20to%20Navigate%20Your%20New%20Global%20Index%20Watch%20Access.pdf) · [QQQ EDGAR 文件](https://www.sec.gov/Archives/edgar/data/1067839/000106783926000030/0001067839-26-000030-index.html) |
| 常规收盘价 | Nasdaq 有历史 NOCP 页面及收盘定义，公开 AAPL 样本页面没有返回历史明细。回填仍须逐证券证明日期、价格类型与拆股基准，并保存原始证据。[Nasdaq NOCP 说明](https://www.nasdaq.com/market-activity/quotes/historical-nocp) · [AAPL NOCP 样本](https://www.nasdaq.com/market-activity/stocks/aapl/historical-nocp) |
| 截点前 TTM GAAP | AAPL 的 SEC `companyconcept` 和 `submissions` 均实测 HTTP 200。季度 2020-03-29 至 06-27 的稀释 EPS 原值为 2.58 USD/股，10-Q（尾号 000062）在 07-30 19:29:09 ET 接收、07-31 记为申报日。10-K（尾号 000096）在 10-29 18:06:25 ET 接收、10-30 记为申报日，同期 EPS 为拆股重述的 0.65 USD/股。重放需按 accession 和可得时间选择版本，再对齐拆股基准。SEC 数据适合验证单个财报事实，重放还需历史篮子、同日收盘和其余季度证据。接收时间与申报日期分别保留，如临界截点需要独立核实发布可得时间。[SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [稀释 EPS API](https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/EarningsPerShareDiluted.json) · [10-Q](https://www.sec.gov/Archives/edgar/data/320193/000032019320000062/0000320193-20-000062-index.htm) · [10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926.htm) |
| 截点前 FY1 normalized | FactSet 文档说明其专用产品保存逐日当时一致预期。ORTEX 明示 normalized 均值、财年结束日、币种与 `Estimate As Of`，但使用其文档提供的 TEST 键访问指数列表及 bulk consensus 均返回 HTTP 403 `insufficientSubscription`。OHLC 的免费层既只含 7 个指定代码，也不含分析师预测；未找到零预算的全名单历史快照。[FactSet PIT](https://www.factset.com/marketplace/catalog/product/factset-estimates-pointintime) · [ORTEX 接口](https://docs.ortex.com/reference/bulk_estimates_consensus_retrieve) · [OHLC 免费与付费范围](https://ohlc.io/pricing) |

归档策略遵照 ADD §7.1 和 SRD AC-16。每个历史点独立要求目标日名单、权重、收盘价、当时可得盈利、对应有效期与窗口内已采证据。TTM 和 FY1 历史轴从各自首个合格点开始；当前预测、当前成分、月末持仓和指数点位不得补作历史估值输入。


## 复核记录与架构准入

| 实测证据 | 定位方式 |
|---|---|
| Nasdaq 匿名权重页 | HTTP 200，空表体；SHA-256 `3deab7a06be717cd481685be1435769093d6ca3df6526cf4ee9f100700b535fb` |
| Invesco 两次持仓响应 | 两次 SHA-256 均为 `ee6dbfc062936a5e40dac73b066a84e634b8800858c7c48d9ef76f6bd9384824` |
| Yahoo AAPL 单次探针 | 价格 `v8/finance/chart` 200，季度 `fundamentals-timeseries` 200，`quoteSummary` 401；完整 JSON 未附 |
| SEC 逐发行人事实 | `https://data.sec.gov/api/xbrl/companyfacts/CIK{10位CIK}.json`；CSV 记录响应 SHA-256、抓取 UTC 和事实 accession。新请求可能因追加申报得到不同哈希 |

- **可以进入软件实施评审。** 优先验证无网络计算内核、导入、合成数据和失败状态。ADD §11 的应用公式、契约、UI、性能和恢复验收需在实现后执行。本轮本地发布试验只验证发布机制样例。
- **真实数据仍受准入约束。** 同日权重与全量常规收盘是共同门槛；TTM 和 FY1 分别要求全部证券口径通过。TTM 可沿 SEC 与发行人原报表路径补齐，FY1 仍需确认具备全量授权及明确期间和会计口径的来源。再次采集应选择开放采集窗口内的交易日。
- **公开真实数据尚未验收。** 实际额度、独立 URL、版本切换及回滚仍需在目标 Vercel 账号上用合成包验证。真实部署另须逐字段解除许可阻塞。调度长期稳定性以真实连续交易日、半日市、休眠和恢复日志验收。当前状态保持为“软件未实施、真实全量未通过、公开真实数据未部署”。
