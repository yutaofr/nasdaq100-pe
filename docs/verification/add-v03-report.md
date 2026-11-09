# ADD v0.3 数据实测报告

核查日为 2026-11-08，时间注明巴黎或纽约。基线为 [ADD v0.3 §13](../ADD.md)，沿用 [v0.1 数据记录](../data-feasibility.md)和 [v0.2 机制记录](add-v02-report.md)。

**本轮完成官方 QQQ CSV 导入实测、100 个 SEC 发行人披露复查、7 项原件季度事实核对和 6 只 FY1 代表证券观察。完整真实 TTM/FY1 仍未通过。** 本轮是周日。11-06 的采集窗口已于巴黎 11-07 18:00 关闭，11-09 窗口尚未开始。下面将正式输入资格、来源能力样本和规则试验分开判定。

| ADD 项 | 本轮结果 | 仍缺证据 |
|---|---|---|
| B-01 同日权重 | 官方导出路径通过一次实测。权重 11-05，11-06 的同日资格未通过 | 开放窗口内连续五个目标交易日的来源推进记录，当前 0/5 |
| B-02 全量价格 | `awaiting_credentials`。用户确认暂无价格凭证或文件，导入及适配器字段契约通过离线验证 | Alpaca SIP 或 Massive 认证、全篮子常规收盘及身份／拆股校验，或具同等证据的真实文件 |
| B-03 TTM | SEC 披露索引全量复查并生成 101 行补证队列，4 份原件补核 | 全篮子最新四季、股类、拆股和价格匹配 |
| B-04 FY1 | 6 只代表证券样本通过网页观察，合格正式及研究输入仍为零 | 逐证券的下一财年、normalized EPS 均值、币种和单位证据 |
| §13.6 研究模式 | 规则探针通过，尚无满足全部门槛的真实组合输入 | 完整可信篮子、合格价格与对应盈利，以及实际应用中的序列隔离 |

## B-01｜官方 QQQ 持仓导出

在 Invesco 官方产品页打开 Portfolio → Holdings → View all → Export data，成功下载 `Complete_Holdings.csv`。下载落盘时间为巴黎 **2026-11-08 22:47:46**，文件尾注明 **2026-11-05**。原件保存在本机下载目录。SHA-256 为 `f2dce85e48d0cc2d5e2e943a55841d0b8690ad3bfaa59c837866e42dc85d302d`。[Invesco 官方持仓页](https://www.invesco.com/us/en/financial-products/etfs/invesco-qqq-trust-series-1.html)

- 页面概览计数为 104，完整导出有 106 行。导出内有 101 只股票及存托凭证，5 条为非股票。101 个代码和 101 个 CUSIP 均唯一，与 v0.1 留存的详细响应逐对匹配。CSV 股票权重和为 99.85%，逐行与详细响应的最大差异为 0.004958 个百分点，与 CSV 两位小数精度相符。已知排除项净权重为 0.17%，另有一项未知，全部排除权重为 `null`。
- 对目标 11-06，导入工具同时记录 `holdings_same_day=false` 和 `holdings_window=missed_window`。基金页面其他区域出现的 11-06 日期属于不同字段，使用 CSV 自带的持仓日期。
- 101 只证券都可以用市值除以份额得到正的隐含估值标记。AAPL 样本为 344.17，与留存 11-05 日线样本约 344.17 一致。该交叉对照未建立全篮子的日期、常规收盘定义和拆股证明，不能把持仓市值反推结果导入为正式价格。
- 五日观察采用官方页面导出或已获准数据路径。当前只验证了一次周日导出，未启动周期抓取。Invesco 网站条款限制自行重复自动访问，公开提供的交互式导出与持续自动采集是两种不同路径。[Invesco 使用条款 §10](https://www.invesco.com/us/en/resources/terms-of-use.html)

### 连续五日记录口径

首批目标 D 为纽约 11-09、10、11、12、13，均待窗口开放。正常收盘后，在纽约 17:30、19:00、22:00，以及次日 00:15、06:15、11:15 观察，纽约次日 12:00 截止。巴黎对应 D 日 23:30 及次日 01:00、04:00、06:15、12:15、17:15，截止 18:00。11-13 的补采仍落在 11-14 周六。每次记录实际观察时间、源日期、导出行数、股票行数、原件哈希和失败码；同日首次可见时间由实际观测给出上界，若前一槽仍是旧日期，则实际到达时间只可定位到两次观测之间。[Nasdaq 交易日历](https://nasdaqtrader.com/Trader.aspx?id=Calendar)

## B-02｜价格导入与补采

用户确认暂无 Alpaca、Massive 凭证或真实价格导出。本轮保留两个认证适配器为 `awaiting_credentials`，没有重复发匿名请求。离线价格契约检查完整同日篮子、逐证券同日 USD 常规收盘、正十进制、来源定位、股类与拆股证据、原件 SHA-256 和采集截点。Alpaca 契约样本要求 `feed=sip` 与 `adjustment=raw`。Massive 样本要求 `adjusted=false` 和个股日结与批量字段的对照证据。结构通过后仍须独立核对数据来源语义，CLI 不签发正式估值资格。[Alpaca 历史行情 FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) · [Massive 个股日结](https://massive.com/docs/rest/stocks/aggregates/daily-ticker-summary)

次日补采按纽约时区模拟验证。Massive 在来源开放前为 `waiting_source`，到次日 00:15 可以尝试，12:00 截止后一秒变为 `missed_window`；半日市的三次次日补采时刻不变。实际供应商开放时间、限额与周末返回行为仍需认证实测。[Massive Basic 数据开放时间](https://massive.com/knowledge-base/article/on-the-free-basic-plan-when-can-i-pull-the-previous-trading-days-data)

### 复跑与文件接口

[离线验证工具](add_v03.py)读取官方持仓 CSV 与可选的标准价格 JSON。持仓复跑示例如下。价格文件通过 `--prices` 指定。

```bash
python3 docs/verification/add_v03.py '/Users/weizhang/Downloads/invesco_qqq_trust,_series_1-Complete_Holdings.csv' \
  --close '2026-11-06T16:00:00-05:00' \
  --observed-at '2026-11-08T22:47:46+01:00'
PYTHONDONTWRITEBYTECODE=1 python3 docs/verification/test_add_v03.py
```

价格 JSON 顶层包含 `data_mode`、`source`、`target_date`、带时区的 `observed_at`、相对 JSON 所在目录的 `raw_file`、`sha256` 及 `prices`。每行记录 `security_id`（本探针对接 CUSIP）、`ticker`、`price_date`、`close`、`currency`、`price_type`、`split_basis_date`、`trading_status`、`source_locator`、`identity_evidence`、`split_evidence`。供应商附加字段由各自契约校验。样例及错误输入见[测试文件](test_add_v03.py)。

## B-03　TTM 披露复查与补证

- **真实复查。** 2026-11-08 巴黎时间 22:47:05–22:47:31，从 EDGAR Submissions 逐发行人发起请求，每批至多 4 个、批次起点间隔至少 1.05 秒。100/100 HTTP 200，101/101 证券代码可与响应 `tickers` 对应。监视定期报告、6-K 及含 2.02/4.02 项的 8-K。在原公司事实抓取后至本轮检查时，未见该筛选范围内的新接收申报。矩阵单独保存 `submissions_checked_at`、原 `content_fetched_at`、候选 accession、接收时间和响应哈希。这次只复查披露索引，`available_at` 仍未知，原财报哈希和抓取时间不变。未对未解析的附件、来源外披露和证券基准作通过判定，也未用此次观察回填 11-06。[EDGAR Submissions 文档](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [SEC 频率政策](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits)
- **补证队列。** 101 行互斥主队列为 Q4 原文件 80、无直接季度标签 7、超 180 天候选 6、币种或境外上市证券口径 3、多股类 2、其他季度或连续性 2、四季候选待基准核对 1。主队列分组后按既有代理篮子权重降序。队列标记依据上一轮 XBRL 与本轮索引筛查，分组数不等于已确认缺失数。同发行人证券保留两行，各行仍需独立核对证券和价格基准。[101 证券复查与补证队列](add-v03-ttm-gap-queue.csv)
- **原件抽样。** 实际下载 4 份 EDGAR 附件，均 HTTP 200。CSV 记录 accession、接收与观察时间、来源哈希和单季值。接收时间不是项目当时已获得的证据。 [单季原件样本](add-v03-ttm-source-samples.csv)

| 证券 | 原件证据和判定 |
|---|---|
| COST | 8-K 附件确认截至 2026-08-30 的 16 周 Q4 稀释 EPS 为 6.75 USD，112 天超出旧的 77–105 天筛选。与留存三个单季 4.50、4.58、4.93 加总得到 20.76 USD 候选。仍需核对整条证券及价格基准。[Costco 8-K 附件](https://www.sec.gov/Archives/edgar/data/909832/000090983226000084/costex9918-k92426.htm) |
| NVDA | 8-K 附件确认截至 2026-01-25 的 Q4 GAAP 稀释 EPS 为 1.76 USD，同一文件另有 non-GAAP 1.62。与留存三个单季 1.30、2.39、2.46 加总得到 7.91 USD 候选。仍需核对整条证券及价格基准。[NVIDIA 8-K 附件](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000019/q4fy26pr.htm) |
| GOOG / GOOGL | 8-K 附件有 2025 Q4 合并稀释 EPS 2.82 USD。2026 Q2 的 10-Q 实际披露 Class A 9.12、Class C 9.11，合并为 9.11，证明将合并 EPS 同时赋给两个股类会出错。两条股类记录保留待逐季补证。[Alphabet Q4 8-K 附件](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000012/googexhibit991q42025.htm) · [Alphabet Q2 10-Q 注 12](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/goog-20260630.htm) |
| ASML | 6-K 财务附件列出最近四季 US GAAP 稀释 EPS 7.34、7.15、7.58、12.93 EUR，加总 35.00 EUR/普通股。发行人确认 NASDAQ 标的是美元报价的美国登记普通股。缺通过验证的换汇政策与当日价格，继续排除于正式 USD 盈利收益率。[ASML 6-K 财务附件](https://www.sec.gov/Archives/edgar/data/937966/000162828026065813/financial_statementsxusx.htm) · [ASML 上市股类说明](https://investor.asml.com/share-information) |

**判定：补证和披露复查已实跑，完整 TTM 未通过。** 上述候选均不进入 11-06 正式指标。后续事件队列按 Q4 原件优先推进，再处理其他标签、口径和过期例外，保留一份原件被多只证券引用的关系。

## B-04｜FY1 代表样本实测

2026-11-08 巴黎时间 22:46–22:49，通过六个可访问的 Stock Analysis 预测页核对下一财年、EPS 符号、报告口径和身份。页面注明 EPS 基于 non-GAAP adjusted，预测数据来自 S&P Global Market Intelligence。公开摘要显示下财年数值，但逐年 EPS Forecast 表中的下财年 `Avg` 单元均要求 Pro，公开页未提供摘要字段到 `EPS Normalized Consensus Mean` 的明确映射。下表数值是展示观察，均未进入计算。

| 样本 | 下一财年末 | 页上下一财年 EPS | 页级 Last updated | 核验结果 |
|---|---|---:|---|---|
| [AAPL](https://stockanalysis.com/stocks/aapl/forecast/) | 2028-09-30 | 10.56 | 2026-11-06 | 当前财年为 FY2027；将 FY2027 均值当作 FY1 会选错期间 |
| [MRNA](https://stockanalysis.com/stocks/mrna/forecast/) | 2027-12-31 | −4.40 | 2026-11-06 | 保留负号；负 EPS 本身不构成缺失 |
| [GOOG](https://stockanalysis.com/stocks/goog/forecast/) | 2027-12-31 | 15.19 | 2026-10-30 | Class C，独立证券键 |
| [GOOGL](https://stockanalysis.com/stocks/googl/forecast/) | 2027-12-31 | 15.19 | 2026-11-06 | Class A，独立证券键；数值相同但页面日期不同 |
| [ARM](https://stockanalysis.com/stocks/arm/forecast/) | 2028-03-31 | 3.08 | 2026-11-05 | 20-F 证实 1 ADS 对应 1 普通股；预测数值仍缺直接的每 ADS / 每普通股及币种证据 |
| [ASML](https://stockanalysis.com/stocks/asml/forecast/) | 2027-12-31 | 56.22 | 2026-10-16 | Nasdaq 报价为 USD，同站财务表为 EUR，预测表无明确币种。发行人把 Nasdaq 证券定义为普通股的注册形式，不能把 QQQ 的 `DRNY` 分类当作 ADR 比例 |

Alphabet 10-K Note 12 证明 A/C 股的股息与清算权益相同，并披露分股类稀释 EPS 方法。这个证据可支持身份映射，但预测来源仍需标明对应证券、股类及单位。ARM 已核实 1∶1 的股数关系，仍需单独确认预测币种。各页 `Last updated` 保存为页级观察，逐条 `revised_at` 保持未知，不能用页面日期或本次读取时间替代。上述网页为交易日窗口关闭后的能力观察。[Alphabet 10-K](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm) · [ARM 20-F](https://www.sec.gov/Archives/edgar/data/1973239/000197323926000097/arm-20260331.htm) · [ASML 证券说明](https://investor.asml.com/share-information) · [ASML EUR 财务表](https://stockanalysis.com/stocks/asml/financials/)

**交叉核验。** Zacks 的 11-02 公开文章明确报告 MRNA 的 2027 年 EPS 共识为 −4.42 USD/股。其说明将共识定义为分析师 EPS 均值，媒体报表将盈利口径定义为扣除非经常性项目（BNRI）。这是负预测及均值的独立证据，具体数值与 11-08 读取的另一家供应商不合并。Zacks 的五个个股详细页请求均返回 403，媒体入口直接访问显示访问验证页。本轮没有经授权的批量下载或全篮子样本。[MRNA 公开文章](https://www.zacks.com/stock/news/3020905/buy-moderna-stock-before-q3-earnings-heres-what-to-know) · [Zacks 均值定义](https://www.zacks.com/upload_education/zrank.pdf) · [BNRI 说明](https://www.zacks.com/media-room/estimates/estimates_reports.php?valtype=SP500)

**接入判定。** S&P 官方查询目录明确存在逐参考日的年度 `EPS Normalized Consensus Mean`，并列出必需数据包，但本轮未获得该产品的实际访问。其文档区分当地证券及存托凭证预测，不能把上游方法直接套到第三方网页摘要。Stock Analysis 官方帮助明确无程序化接口，服务条款允许遵守 robots.txt 的搜索索引等访问，但没有为本项目建立全量自动采集路径。六个样本均未通过项目的完整准入。本轮无合格的严格或研究 FY1 组合，亦无可信同日权重分母可报告覆盖率。[S&P 字段查询目录](https://www.marketplace.spglobal.com/en/support/query-library/query-%286350%29) · [S&P 口径方法](https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates) · [Stock Analysis API 说明](https://stockanalysis.com/help/faq/api-access/) · [Stock Analysis 条款](https://stockanalysis.com/terms-of-use/)

## §13.6｜研究模式与复查边界

7 组探针零失败，覆盖实际 CSV 结构所用解析规则、数据补采时钟、价格文件证据校验、固定篮子交易日差第 5/6 日、缺完整权重的子集拒绝、子集负值和零值、周度观察自然日第 7/8 日、预测修订第 30/31 日、严格／研究模式键隔离，以及在线重新核验与过期离线缓存的区别。模式键用例验证方法分区，应用历史和发布队列仍需集成验收。

截至本报告，D 日正式权重分母未知，TTM、FY1 正式覆盖率均为 `null`。本轮没有发布估值、回填历史或产生真实研究组合。首次正式窗口实测仍须同时取得同日权重和合格全篮子收盘价，随后分别判定 TTM 与 FY1。
