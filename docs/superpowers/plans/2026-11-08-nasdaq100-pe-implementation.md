# 纳指100估值看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付零数据采购预算、本机个人使用的中文估值看板，提供有原件证据的整体估值引用、观察历史、导出和严格标注边界的自主计算研究。

**Architecture:** 来源引用走独立校验、归档和发布路径，不依赖证券计算引擎。研究输入经身份、权重、价格、盈利及模式校验后由唯一 Decimal 内核计算；不可变文件为审计依据，SQLite 索引可重建，React 仅消费版本一致的静态发布包。

**Tech Stack:** Python / Decimal / JSON Schema / SQLite；TypeScript / React / Vite / CSS；pytest、前端组件测试及浏览器端到端测试。具体版本在 T01、T05 实施时锁定，本计划不宣称已安装或已验证版本兼容性。

**Spec:** [ADD v1.0](../../ADD.md)，优先级为 §0 定稿要求 > §13 对保留设计的修订 > 其他 ADD 条款 > [SRD v0.3](../../SRD.md)。参考 [v0.3 实测报告](../../verification/add-v03-report.md)，历史探针不是应用验收证据。

## 1. Global Constraints

- 默认 `deployment_mode=local_private`，HTTP 只绑定 `127.0.0.1`；数据采购预算为零。
- 首版必须有至少一条真实滚动 PE 和一条真实 Forward PE，均关联原件；二者无需证明同口径，未知项为 `unknown`。
- 来源引用不进入自算 engine，不衍生“100元盈利”、跨来源变化率或盈利增长率；Forward PE 不自动等于 FY1 normalized。
- 金额、价格、EPS、权重、收益率和 PE 使用十进制字符串；缺失为 `null`，已知零为 `"0"`，拒绝 NaN/Infinity。
- Decimal 为34位有效数字、half-even；计算误差验收≤1e−10；官方权重和的舍入修正容差为0.0001。
- 日期 `YYYY-MM-DD`；时间戳带时区，归档 UTC；交易日按 `America/New_York`；研究明确展示 W（篮子日）/D（价格日）/T（观察时点）。
- `strict` 固定 current/full/daily；research 的固定篮子最多滞后5交易日，周度观察最多7自然日；最新季度年龄≤180自然日，已知预测修订年龄≤30自然日。
- strict 截止为 D 后一个自然日纽约12:00；观察时点研究不套用该截止，不把观察时获得的信息回填成 D 日历史。
- 本地 JSON 导入上限20MiB；来源链接限许可 HTTP(S)；不执行导入内容、不自动访问导入 URL。
- `DATA_ROOT` 在服务目录之外。原件、配置、凭证、完整异常栈不进入静态包；前端资源本地打包。
- 完整 TTM、完整 FY1、无人值守和公网发布分别验收，均不阻塞满足 ADD §0.5 的首版交付。

## 2. 基线、任务管理与完成定义

当前目录只有设计、可行性报告和验证探针，没有应用骨架，也不是 Git 仓库。本次只新增计划；不初始化 Git、不安装依赖、不执行产品开发、不改写旧报告。下列路径与接口是实施约定，尚未存在。类型未逐字段展开的实体，以 ADD §0.2、§4、§13.6 为字段定义，由 T01/T07 的 schema 固化。

除特别标明完整路径外，任务文件清单中的同组短路径沿用该组首个路径的代码根目录；例如 `published/importer.py` 为 `src/nasdaq100_pe/published/importer.py`，前端 `src/components/` 为 `apps/web/src/components/`。

任务状态统一为 `todo / in_progress / blocked / in_review / done`，初始全部 `todo`。每条验收项均须登记测试名或证据文件；有一项必选标准不满足，该任务不得 `done`。数据任务可按标准交付“明确缺口”，但不能因此勾选完整数据验收。负责人按角色分配，实施启动时填实际承担者。

每项代码任务执行以下步骤，并使用本任务列出的验收条件补齐测试断言：

- [ ] 先写对应失败用例；运行任务指定命令，确认失败原因是目标能力缺失。
- [ ] 实现本任务列出的接口及文件，避免扩大到后续任务。
- [ ] 运行指定测试及受影响的契约/集成测试，保存结果。
- [ ] 逐条核对验收条件、说明已知限制，交付评审；若届时已有 Git 仓库，按任务提交，未有则保留文件变更记录，不伪造提交记录。

真实数据任务以采集/核对记录替代“先写失败测试”，不能用 mock 通过替代真实验收。本文中的测试命令均为未来实施验收命令，未执行；测试工具由对应骨架任务配置。

## 3. Review Focus

以下五类风险必须落到测试，不只留在评审说明中：

1. 网页报价日期被误当作 PE 日期，导致旧数据显示“最新”：T01、T05、T06 检查 `source_as_of=null` 的完整链路。
2. 周日读取周五价格，被错误拒绝或回填成周五历史：T09、T14 验证研究可记录于 T，strict 拒绝超窗新输入。
3. 覆盖率显示100%或零权重缺失掩盖不完整：T08、T11 验证成员完整性与覆盖率独立。
4. 原件/缓存未变，最新性时间被刷新冒充新证据：T02、T12 验证 content_fetched_at 与 checked_at 分离。
5. 旧请求/旧修订迟到，使日期标题、卡片或发布指针回退：T03、T05、T11、E04 验证原子切换和排序。

## 4. 里程碑与依赖

| 阶段 | 任务 | 可验收产物 | 放行条件 |
|---|---|---|---|
| M1 引用闭环 | T01—T06 | 真实引用导入→归档→本机首页→历史→导出 | T06 两类真实引用通过；此时尚不宣称首版全部完成 |
| M2 研究软件 | T07—T11 | 完整篮子校验、计算、研究模式、研究页 | 公式/负值/缺失/子集/模式隔离通过；真实数据不足有具体缺口 |
| M3 数据补证与首版交付 | T12—T14 | 价格/TTM接入与缺口报告、交付证据 | T14 首版验收矩阵全部必选轴通过 |
| 后续增强 | E01—E05 | 完整指标、无人值守、可选公网 | 各自独立放行，不倒置为首版依赖 |

依赖：T01→T02→T03→T04→T05→T06；T07依赖T01/T02，T08依赖T07，T09依赖T07/T08，T10依赖T03/T04/T09，T11依赖T05/T10，T12依赖T07/T09，T13依赖T07/T08/T09/T12，T14汇总T01—T13。T06和T07—T09可独立安排人员推进；这是排期建议，不要求创建子代理。

文件职责：`schemas/`定义交换契约；`src/nasdaq100_pe/published/`管理引用；`identity/normalize/validate/engine/`管理研究；`archive/`管理文件和索引；`publisher/`管理发布；`adapters/`管理来源；`apps/web/`只负责展示。不要把 `docs/verification/` 的历史脚本直接作为生产模块。

## 5. 首版实施任务

### T01｜引用数据契约与人工导入校验

**优先级/负责人/依赖：** P0；后端；无。对应 ADD §0.2、§4.1、§8.3、§10。

**文件：** 新建 `pyproject.toml`、Python依赖锁文件、`schemas/published-observation.schema.json`、`src/nasdaq100_pe/published/models.py`、`published/importer.py`、`cli.py`、`tests/published/test_import.py`。

**接口：** `validate_published(payload: bytes) -> PublishedImportResult`；新增 `ndx-pe import-published --file INPUT`，不改研究 `import` 的含义。输出 `observations`、字段级 `diagnostics`、`completeness`、`publication_status`；校验阶段不发布。

**验收标准：**

- [ ] schema覆盖 ADD §0.2 全部字段；补充 `schema_version`、`data_mode=real|synthetic`；`metric_kind=trailing_pe|forward_pe`，数值以有限十进制字符串表示。
- [ ] 正确输入分别接受滚动与前瞻指标；`source_as_of=null` 合法；原名、来源、观察时间、原件哈希及定位不可缺少。日期/单位/枚举不合法、重复 observation_id、数字型 value、超20MiB均拒绝，退出2并列字段路径。
- [ ] 未知期间、会计和亏损处理保存unknown；不得根据forwardPE名字补成FY1或normalized，不得根据页面报价日期填写source_as_of。
- [ ] 输入结构错误不写观察记录、不产生release；原件核验失败由T02拒绝，不允许只有字符串哈希就认定证据成立。
- [ ] CLI已可从锁定环境安装运行；`--help`区分引用导入和研究导入。恶意URL或本地路径字段不会触发下载或执行。

**验证：** `python -m pytest tests/published/test_import.py -q`。关键用例 `test_quote_date_not_metric_date`、`test_unknown_basis_preserved`、`test_oversize_rejected`。

### T02｜证据归档、观察历史与修订

**优先级/负责人/依赖：** P0；后端；T01。对应 ADD §0.2、§7.3—7.4。

**文件：** 新建 `src/nasdaq100_pe/archive/evidence.py`、`archive/store.py`、`archive/index.py`、`published/history.py`、`tests/archive/test_store.py`、`tests/published/test_history.py`。

**接口：** `archive_published(result: PublishedImportResult, evidence_files: Mapping[str, Path], store: ArchiveStore) -> ObservationBatch`；`list_observations(series_key: str) -> list[PublishedMetricObservation]`。series_key包括provider、instrument、原名、kind、口径/方法标识、data_mode；修改任何口径产生新序列。

**验收标准：**

- [ ] 原件复制到私有raw目录，实际SHA-256与声明值一致；原件缺失、哈希不符或路径越出显式证据目录时失败，无半条成功索引。
- [ ] 观察时间保持真实，source_as_of和获取时间不相互替代；重复导入完全相同ID/内容幂等；同ID不同内容拒绝，更正须新ID并显式关联原观察及原因。
- [ ] 来源、口径及真实/演示分序列；同一旧factsheet的再次检查记录检查时间，但不更新其数据日期，不伪造新发布数据。
- [ ] 文件不可变；在“文件写完、索引事务前”注入崩溃后可从manifest重建索引，暂存文件不算成功归档。索引删除重建后记录数和哈希一致。
- [ ] 导入日志只保留允许字段，不含原始响应、秘密URL参数或完整异常栈。

**验证：** `python -m pytest tests/archive/test_store.py tests/published/test_history.py -q`；保存故障恢复前后的manifest比较。

### T03｜引用发布包与版本原子切换

**优先级/负责人/依赖：** P0；后端；T02。对应 ADD §0.2、§3、§7.3—7.4、§8。

**文件：** 新建 `schemas/local-release.schema.json`、`src/nasdaq100_pe/publisher/local.py`、`publisher/pointer.py`、`publisher/sanitize.py`、`tests/publisher/test_local.py`。

**接口：** `build_local_release(selection: ReleaseSelection, store: ArchiveStore) -> Release`；`promote_release(release_id: str, expected_current: str | None) -> PromotionResult`；新增 `ndx-pe build-local --observations BATCH_ID`，后续兼容ADD的 `--snapshot ID`。

**验收标准：**

- [ ] 无证券输入也能构建引用包；manifest、观察历史、方法、清洗后的运行状态和哈希均属于同一release；引用发布不调用engine。
- [ ] 本机public权限unknown/denied仍可构建；不生成public目录或访问云端。
- [ ] 缺引用文件、schema不符、哈希不符、秘密扫描命中时拒绝提升指针，保留最后成功版本，退出6。
- [ ] 候选包完整写入后原子重命名；并发提升采用锁/CAS。同序列旧修订不能覆盖新修订；显式rollback单独留审计记录。
- [ ] 静态产物、source map、错误状态中不含DATA_ROOT、令牌、原始归档或内部堆栈；原件哈希与安全来源定位可以展示。

**验证：** `python -m pytest tests/publisher/test_local.py -q`，含 `test_late_revision_cannot_replace_current`、`test_public_denied_allows_local` 和秘密注入测试。

### T04｜回环只读服务、导出及手动操作闭环

**优先级/负责人/依赖：** P0；后端；T03。对应 ADD §4.4、§8.1/8.3、§10。

**文件：** 新建 `src/nasdaq100_pe/server.py`、`export.py`、`tests/test_server.py`、`tests/test_export.py`；修改 `cli.py`。

**接口：** `serve_local(root: Path, host: str, port: int) -> None`；`export_published(batch_id: str, output: Path) -> ExportManifest`；CLI `serve --host 127.0.0.1`、`export --observations ID --scope local`、`status`。

**验收标准：**

- [ ] 实际监听地址仅127.0.0.1；请求0.0.0.0绑定直接拒绝。合法localhost/回环Host可读；非法Host、路径穿越、编码穿越、指向私有目录的符号链接不可读。
- [ ] 无release首次启动健康检查可用，返回明确空状态；服务无上传、更新、配置接口，不开放CORS，不以工作目录为根。
- [ ] 候选release经HTTP读取校验后才提升；服务不可用时保留归档和旧指针，手工重试不重复导入。
- [ ] JSON导出保留精确值、时间、原名、模式和来源证据引用；CSV＋metadata包含固定字段、单位和口径，负数数值不被错误转为文本，`= + - @`开头文本转义。
- [ ] 导出不夹带凭证、私有绝对路径或原件全文；引用包明确不是自算复算包。重导入JSON后业务字段一致。
- [ ] status分别显示导入/归档/发布状态，退出0不代表完整数据；输入错误2、存储/服务错误6按ADD区分。

**验证：** `python -m pytest tests/test_server.py tests/test_export.py -q`；保存真实HTTP探测和监听地址证据。

### T05｜中文引用首页、观察历史与周度检查状态

**优先级/负责人/依赖：** P0；前端；T04。对应 ADD §0.1—0.4、§9。

**文件：** 新建 `apps/web/package.json`、前端依赖锁文件、`src/data/ReleaseProvider.tsx`、`src/pages/PublishedPage.tsx`、`src/components/PublishedMetricCard.tsx`、`src/components/ObservationHistory.tsx`、`src/styles.css`、`src/pages/PublishedPage.test.tsx`、`e2e/published.spec.ts`；新增 `src/nasdaq100_pe/published/checks.py`及测试。

**接口：** 前端 `loadRelease(releaseId: string, signal: AbortSignal): Promise<LocalRelease>`；CLI新增 `ndx-pe check-published --series KEY --evidence FILE`，记录来源检查事件，不能直接修改指标原件或日期。

**验收标准：**

- [ ] 默认“整体估值参考”，独立滚动/Forward卡片；各卡片显示来源、原名、单位、source_as_of、observed_at、口径限制和来源链接。
- [ ] 未注明日期显示“来源未注明，观察于…”；过期原件保留原日期。周度检查到期以最后有证据的检查时间＋7自然日计算，超过期限显示“周度检查逾期”；仅刷新页面不改变检查时间。
- [ ] 方法未披露显示unknown对应中文说明，不出现100元解释、跨来源增长率，卡片缺一类时不以另一类或研究结果替代。
- [ ] 来源和口径各自独立历史，按真实observed_at归档，不回填；0点空状态、1点积累提示，多点提供同序列表格。未发生的检查不补造记录。
- [ ] 慢请求A在快请求B后返回时整屏仍是B；失败保留上一可核实版本及日期，同时显示失败。所有组件使用同一release。
- [ ] 页头常驻本机/真实或演示标识；研究入口独立；无研究数据不影响引用首页。来源文本转义，危险协议链接不渲染。
- [ ] 320/390/768/1440px页面不横向溢出；键盘可操作历史/导出/导航，焦点可见，状态有文字；无第三方分析或外部字体请求。

**验证：** `npm --prefix apps/web run test -- --run`；`npm --prefix apps/web run test:e2e -- published.spec.ts`；`python -m pytest tests/published/test_checks.py -q`。

### T06｜两类真实引用数据验收（M1关卡）

**优先级/负责人/依赖：** P0；数据核验＋测试；T05。对应 ADD §0.5。

**文件：** 新建 `docs/acceptance/published-real-data.md`；真实原件/输入仅放 `DATA_ROOT/raw/`、`inputs/`，不复制到合成fixtures或网站目录。

**交付：** 至少一条真实滚动PE、一条真实Forward PE及各自原件、定位、核验记录、页面和导出结果。

**验收标准：**

- [ ] 在实际执行时从可访问的候选来源核对指标，记录真实观察时间、URL、原件哈希及页/表定位；不复制ADD曾观察数值充当当前数据。
- [ ] 复核人可由原件定位到相同数值、单位和原名；缺日期/亏损处理/normalized依据均明确未知。两条记录可以不同来源，不要求同口径。
- [ ] 使用正式CLI导入、构建、HTTP打开、导出；页面/JSON/CSV的数值和日期一致，证据链可回查，报告记录命令、退出码、observation/release ID。
- [ ] 断开外网后仍可浏览已发布内容和本地导出；真实标识正确，没有合成占位数值。
- [ ] 某类来源无法核实时记录该关卡blocked及缺口；M1真实引用不通过，不能用“软件已通过”代替。

**验证：** 人工双向核对“原件→输入→页面/导出”，运行T01—T05相关回归；报告分别标记软件和真实数据结论。

### T07｜研究输入、永久身份及完整篮子

**优先级/负责人/依赖：** P0；后端/数据；T01/T02。对应 ADD §4、§5.1—5.3、§13.3。

**文件：** 新建 `schemas/research-input.schema.json`、`src/nasdaq100_pe/identity/models.py`、`normalize/holdings.py`、`validate/basket.py`、`validate/input.py`、`tests/validate/test_basket.py`、`tests/validate/test_identity.py`。

**接口：** `validate_research_input(payload: bytes, policy: MethodSpec) -> InputValidation`；`normalize_holdings(raw: bytes, evidence: SourceEvidence) -> tuple[Universe, WeightSet]`。输出保留原始值、排除项、归一化/舍入系数及诊断；不产生PE。

**验收标准：**

- [ ] 不固定100/101只，按有完整性证据的集合校验；仅前十大、重复/漏股票、未知资产类别、仅complete=true均不能形成合格篮子。
- [ ] 股票集合完整、非股票权重部分未知时允许代理按股票和归一化，保留known_excluded_weight和unknown_excluded_items，total_excluded_weight=null。
- [ ] 官方权重和与1之差恰为0.0001允许修正，超过拒绝；负权重拒绝。代理归一化系数与官方舍入修正系数分别存储。
- [ ] GOOG/GOOGL稳定证券ID和股类分别存在，可共享发行人CIK；代码改名有生效区间，CUSIP不代替永久ID；ADR比例及范围无证据不得猜测。
- [ ] 无可信完整权重时coverage_ratio=null且显示“完整权重未知”；不输出0%或以返回证券数充当分母。
- [ ] 原始证据、候选标准化、语义合格、日期合格分别记录；单条盈利无效可保留诊断，整批篮子结构错误退出4，不发布计算快照。

**验证：** `python -m pytest tests/validate/test_basket.py tests/validate/test_identity.py -q`；加入实际官方CSV结构的去敏fixture，但不宣称fixture证明当前完整篮子可用。

### T08｜唯一计算内核、行业与派生指标

**优先级/负责人/依赖：** P0；后端；T07。对应 ADD §6、SRD AC-01—08。

**文件：** 新建 `src/nasdaq100_pe/engine/core.py`、`engine/sectors.py`、`engine/derived.py`、`schemas/calculation-result.schema.json`、`fixtures/synthetic/formula-cases.json`、`tests/engine/test_core.py`、`tests/engine/test_sectors.py`、`tests/engine/test_derived.py`。

**接口：** `calculate(inputs: ValidatedInputs, method: MethodSpec) -> CalculationResult`；不读网络/系统时钟，不访问引用指标。ValidatedInputs由T07结构校验与T09资格校验共同产生，T08先用明确标识的合成对象测试。

**验收标准：**

- [ ] PE为30/40/400/120/−40、权重.3/.3/.2/.1/.1时，Y≈0.016333333333、PE≈61.2244897959；50% PE10＋50% PE20得到Y=.075、PE≈13.333333，误差≤1e−10。
- [ ] 负盈利保留负贡献；EPS=0且价格有效计入覆盖，收益率0；PE=0不能推导零盈利。完整且Y≤0时pe=null、pe_state=non_positive，保留Y。
- [ ] 任一成员盈利缺失（包括零权重）均非complete；即使显示覆盖四舍五入100%也不输出完整PE/portfolio_yield，保留K、C及缺失ID。TTM/FY1各自判定。
- [ ] 行业完整才输出其Y/PE；零行业权重、未分类、部分覆盖均有定义；行业K和W加总与组合一致，贡献百分点评价为100×c_i。
- [ ] 公司市值按发行人去重；同发行人冲突、日期/币种/公司范围未证实时总市值不可用，但EPS路径仍可计算。不得以公司市值替换证券权重。
- [ ] 完整收益率才显示100×Y；增长比较须同篮子/价格、双方正值且会计口径可比；默认GAAP/normalized隐藏盈利增长。PE差异若显示须附“不同盈利口径下的估值差异”。
- [ ] 输入排序变化结果相同；34位half-even，不先展示舍入；有冲突的多计算路径不平均，未经验证的利润/市值路径不启用。

**验证：** `python -m pytest tests/engine -q`；数值断言用Decimal和固定容差，不比较网页两位小数代替算法验收。

### T09｜研究资格、时钟政策及子集计算

**优先级/负责人/依赖：** P0；后端；T07/T08。对应 ADD §0.3、§13.3—13.6。

**文件：** 新建 `src/nasdaq100_pe/calendar.py`、`validate/eligibility.py`、`engine/subset.py`、`config/methods.json`、`tests/validate/test_profiles.py`、`tests/engine/test_subset.py`。

**接口：** `assess_eligibility(inputs: InputValidation, context: AnalysisContext, calendar: TradingCalendar) -> ValidatedInputs`；`calculate_subset(result: CalculationResult, metric: str) -> SubsetResult`。AnalysisContext显式注入W/D/T、analysis_profile/basket_policy/coverage_policy/freshness_policy及method_version。

**验收标准：**

- [ ] strict仅current/full/daily；组合不合法拒绝。研究周日T读周五D可通过时间入口，归档点为T；同一新输入用于strict D则超窗拒绝。
- [ ] fixed篮子要求W≤D，已验证交易日差5可用、6拒绝新计算；日历未知无法猜差值。休市/半日/夏令时有版本化日历fixture测试。
- [ ] 固定旧权重不按价格漂移；已知退市、并购或无法定价成员不删除重归一化；必须通过身份和拆股检查，index_comparability=unverified。
- [ ] 有完整篮子分母时C>0才可算子集K/C、正K才有PE=C/K；C=0不可用，K=0或负保留收益率且PE非正状态；完整权重未知一律禁止子集覆盖。
- [ ] 子集名称分别为“已覆盖证券子集TTM估值”/“已覆盖证券子集FY1估值”，列覆盖权重、数量、排除清单和“并非全指数”；95%不升级complete。
- [ ] weekly最多7自然日获取年龄且跨度不超过7日，恰7有效、第8日失效；daily最新性核验年龄必须小于24小时，恰24小时须重新核验；FY1修订30日有效、31日无效、未知允许但标FORECAST_FRESHNESS_UNVERIFIED；TTM季度180/181日边界通过。
- [ ] 所有模式字段、W/D/T及集合哈希进入输入身份和序列键；strict/研究、full/subset、daily/weekly、real/synthetic不相互覆盖或连线，周度模式不得用于增长比较。

**验证：** `python -m pytest tests/validate/test_profiles.py tests/engine/test_subset.py -q`。时钟由fixture注入，不依赖执行当天日期。

### T10｜研究CLI、不可变快照、复算和本地发布

**优先级/负责人/依赖：** P0；后端；T03/T04/T09。对应 ADD §4.4、§7.2—7.4、§10。

**文件：** 新建 `schemas/snapshot.schema.json`、`src/nasdaq100_pe/pipeline.py`、`archive/snapshots.py`、`tests/integration/test_research_pipeline.py`；修改 `cli.py`、`export.py`、`publisher/local.py`。

**接口：** `run_import(path: Path, context: AnalysisContext) -> RunRecord`；`recompute(snapshot_id: str) -> Snapshot`；实现 `validate --input`、`import --file`、`recompute --snapshot`、`export --snapshot --scope local`、`build-local --snapshot`。

**验收标准：**

- [ ] 结构可信且部分盈利无效可归档partial，退出0但JSON明确completeness与publication_status；缺完整篮子/必要价格集不发布新计算快照，保留输入诊断和旧发布。
- [ ] 规范化排序/时间/Decimal后哈希；input_hash＋method/engine/schema版本决定计算身份，run_id不参与。相同归档输入复算一致，新获取时间是新证据，不强行去重。
- [ ] 更正生成新快照并保留supersedes、原因、时间和revision_seq；旧快照可读，普通发布不得回退到旧修订。
- [ ] 完整JSON复算包带输入/证据引用/政策/结果，导入复算一致；CSV带metadata、模式、缺失原因及精确值，遵守T04转义规则。
- [ ] 新partial与上次complete并存，默认显示新日期质量状态并链接上次完整；不将旧PE填入新日期。
- [ ] 引用和研究同站共存但各自版本选择隔离；研究失败不清空引用首页。归档后发布失败可复用同一快照重试，不重算/重采。

**验证：** `python -m pytest tests/integration/test_research_pipeline.py -q`，含复算一致、崩溃恢复、旧修订迟到和两路径故障隔离。

### T11｜自主计算研究页、明细、行业和历史

**优先级/负责人/依赖：** P0；前端；T05/T10。对应 ADD §0.3—0.4、§9。

**文件：** 新建 `apps/web/src/pages/ResearchPage.tsx`、`src/components/QualityBanner.tsx`、`OverviewGrid.tsx`、`SectorView.tsx`、`ConstituentTable.tsx`、`ResearchHistory.tsx`、`e2e/research.spec.ts`及组件测试。

**接口：** 消费T10 Snapshot，复用T05 ReleaseProvider；前端只格式化，不重算权重、覆盖或PE。

**验收标准：**

- [ ] 名称含“观察时点研究”，代理明确“纳指100估值估算（QQQ股票持仓代理）”；fixed另显“QQQ历史权重固定篮子研究”，weekly显“非同步周度观察”；W/D/T、模式和差异限制同屏可见。
- [ ] 覆盖、缺失清单、TTM/FY1独立状态可查；分母未知显示“完整权重未知”。无真实研究输入显示具体缺口，不默认显示合成数值。
- [ ] 研究概览≥360px两列三行、低于360单列，顺序遵循ADD §9；PE两位＋倍，收益率/权重两位百分数；极小非零不显示为0，详情精确值可查。
- [ ] 缺失“—＋原因”、非正“N/M（盈利非正）”、个股负PE“亏损”；完整结果的100元解释与跨口径限制符合T08，引用区不出现这些派生解释。
- [ ] 表列与ADD一致，默认权重降序，原始精度排序、空值始终底部、同值按证券ID；搜索/行业/状态筛选仅影响明细及计数，概览不变。
- [ ] 行业选择可清除；手机名称列固定和横滑提示，表头固定、页面无横向溢出；键盘可操作所有筛选/排序/详情，图表有等价表格。
- [ ] 方法/模式切换不跨序列连线。研究观察历史按T，不把周度观察间隔标成缺交易日；strict历史按日历断点，周末不误判。N/M和partial不当作完整数值点，单点不画趋势。
- [ ] 日期切换乱序请求不产生混合快照；失败保留可核实旧日期并说明失败；四种视口及真实/演示隔离通过。

**验证：** `npm --prefix apps/web run test -- --run`；`npm --prefix apps/web run test:e2e -- research.spec.ts`。

### T12｜真实价格导入、来源接入边界与缺口矩阵

**优先级/负责人/依赖：** P0；数据/后端；T07/T09。对应 ADD §5、§12 B-02、§13.2。

**文件：** 新建 `src/nasdaq100_pe/adapters/base.py`、`adapters/price_file.py`、`validate/prices.py`、`tests/adapters/test_price_file.py`、`docs/acceptance/research-price-coverage.md`。认证供应商实现留E01。

**接口：** `load_prices(path: Path, universe: Universe, context: AnalysisContext) -> PriceBatch`；PriceBatch包含逐证券标准价格、证据及状态。预留 `fetch_prices(target_date: date, security_ids: Sequence[str]) -> PriceBatch` 接口契约。

**验收标准：**

- [ ] 每证券检查D日、正值、USD/币种政策、常规收盘、股类及拆股基准、原件哈希和定位；盘后价、旧价、持仓市值/份额反推价、只叫close而口径未知的值不作为合格正式价格。
- [ ] 全集合输出矩阵，缺失/停牌/身份变更/拆股不明分别有原因；不能仅验证AAPL就标全量通过，不以旧价填缺。
- [ ] 实施时有可用真实文件则按正式CLI核验；没有则报告 `awaiting_user_import`，列缺哪些字段和证券。凭证未提供时接口状态为awaiting_credentials，不反复匿名请求。
- [ ] 离线契约覆盖Alpaca要求SIP/raw和Massive adjusted=false的元数据；契约通过不声明供应商实接通过，也不自动以IEX代替SIP。
- [ ] 真实输入成功才允许研究计算；若缺必要价格集，页面显示缺口。此任务可以“软件＋真实缺口报告”完成，完整真实价格轴保持未通过。

**验证：** `python -m pytest tests/adapters/test_price_file.py -q`；报告列每证券状态和证据路径，不用null完整分母计算覆盖百分数。

### T13｜TTM补证、最新性复核与逐证券盈利导入

**优先级/负责人/依赖：** P0；数据/后端；T07/T08/T09/T12。对应 ADD §5.3、§13.4—13.5。

**文件：** 新建 `src/nasdaq100_pe/adapters/sec.py`、`normalize/quarters.py`、`validate/earnings.py`、`research/gap_queue.py`、`tests/adapters/test_sec.py`、`tests/validate/test_earnings.py`、`docs/acceptance/ttm-evidence.md`。

**接口：** `fetch_earnings(issuer_id: str, context: AnalysisContext) -> EarningsBatch`；`validate_earnings(batch: EarningsBatch, identities: Sequence[SecurityIdentity]) -> EarningsValidation`；`build_gap_queue(inputs: InputValidation) -> list[EvidenceGap]`。

**验收标准：**

- [ ] SEC按发行人获取再映射证券，同CIK不合并股类；默认TTM为四个明确已报告、连续最新季度GAAP稀释EPS之和，保存reported_quarter_eps_sum及逐季定位。
- [ ] 合法16周季度可通过；Q4缺失不可用全年EPS减九个月补齐；四季和与全年差异保留，不强制抹平。自动解析不确定转待人工复核，不挑最接近值。
- [ ] 回归覆盖MRNA负值、GOOG/GOOGL股类差异、COST特殊季长、ASML EUR/USD不匹配、拆股基准不一致及ADR单位未明；不合格行不进入对应指标。
- [ ] checked_at只有实际查询最新披露成功才更新；content_fetched_at及原哈希不变；离线重读不刷新，复核失败不能冒充最新。新增披露/重述产生新版本和补证任务。
- [ ] 队列先按缺Q4/缺标签/币种ADR/股类/过期等分类，组内按权重排；低权重不被删除；每缺口关联证券、来源与待补证内容。
- [ ] FY1文件可验证期间、财年末、mean、normalized、单位/币种、更新时间证据；只有forwardPE或网页non-GAAP标签不足时拒绝FY1，TTM不受影响，未知修订时间单独质量标记。
- [ ] 运行一轮可用来源/本地原件核对并记录真实结果；若来源不可用或证据不足，保留未完成矩阵，不把旧探针结果迁移为合格数据。首版无需补齐全篮子。
- [ ] 请求有速率上限、退避和User-Agent配置；401/429不无限重试，日志不泄露响应和秘密；不引入付费路径。

**验证：** `python -m pytest tests/adapters/test_sec.py tests/validate/test_earnings.py -q`；附一次实际核验记录、队列及已合格/未合格样本，不用HTTP 200代替口径验收。

### T14｜首版集成、安全、性能与交付验收（最终关卡）

**优先级/负责人/依赖：** P0；测试/技术负责人；T01—T13。对应 ADD §0.5、§8、§11。

**文件：** 新建 `README.md`、`config/example.json`、`docs/acceptance/release-v1.md`、`tests/integration/test_release_acceptance.py`、`apps/web/e2e/acceptance.spec.ts`、`scripts/verify-local.sh`、`src/nasdaq100_pe/archive/backup.py`及恢复测试。

**交付：** 可重现安装与手工导入/检查/构建/serve/导出/复算说明、锁文件、首版证据报告和备份恢复操作。

**验收标准：**

- [ ] 新环境按README和锁文件安装，可完成两类真实引用的完整闭环；手动serve满足首版，不要求安装launchd或云账号。
- [ ] T01—T13全部必选标准有测试或证据；研究无合格真实输入时展示具体缺口，引用首页仍可用。真实/演示在输入、历史、发布、导出四层均隔离。
- [ ] 实际HTTP验证回环/Host/目录隔离、恶意来源文本、CSV公式防护、静态产物秘密检查；非法导入不会损坏最后成功版本。
- [ ] 备份命令可复制私有归档、索引、方法及身份映射到独立本地目录；从备份重建索引并复算一份快照一致。未配置备份时status明确无恢复保障；每日自动备份留E04，不宣称已有异地备份。
- [ ] 约110条合成证券、固定Chromium、390×844、冷缓存、4倍CPU降速、10Mbps/1Mbps/100ms RTT，5次LCP均≤3秒，报告中位数和最差值；首屏只请求当前快照，压缩传输目标≤500KiB，若调整必须记录理由并重新评审。
- [ ] 320/390/768/1440px与键盘操作、迟到请求、空/失败/partial/N/M状态均通过；无PE红绿估值阈值、买卖信号或无依据十年百分位。
- [ ] 验收报告分别记录：真实引用通过；本机软件通过；本机部署通过；研究功能通过；完整真实TTM未完成或附独立通过证据；完整真实FY1未完成或附独立通过证据；无人值守未验；公网首版不适用。
- [ ] 所有历史报告保持原判定；未完成项写明影响和后续任务ID，不把设计定稿、探针通过或退出0写成产品/数据全部通过。

**验证：** `python -m pytest tests -q`、`npm --prefix apps/web run test -- --run`、`npm --prefix apps/web run build`、`npm --prefix apps/web run test:e2e`及真实操作记录。只运行在新产品tests中的验收套件；历史网络探针不自动纳入回归。

## 6. 后续增强任务（不计入首版完成条件）

以下任务有独立验收标准；实施前核对来源访问条件和资源实际可用性，不因列入计划自动购买服务或发布公网。

### E01｜认证价格适配与严格窗口完整篮子验证

**依赖/负责人：** T12/T14；数据/后端。对应 ADD §5、§12 B-01/B-02、§13.2—13.3。

**文件/接口：** 新建 `src/nasdaq100_pe/adapters/alpaca.py`、`src/nasdaq100_pe/adapters/massive.py`、`tests/adapters/test_authenticated_prices.py`、`docs/acceptance/strict-inputs.md`；实现T12的fetch_prices契约。

- [ ] 有可用免费凭证才实接；无凭证保留awaiting_credentials。逐证券确认SIP/raw或经日结对照证明的Massive常规收盘，检查全篮子，不以单股成功放行。
- [ ] 连续5个真实目标交易日记录完整QQQ股票集合、权重真实日期、观察时间、原件哈希和最早可见区间；来源仍D−1则当日strict不通过。
- [ ] 每个D的所有必需输入在D后一个自然日纽约12:00前实际取得；截止前成功、截止后一秒拒绝；来源未开放记waiting_source而非网络失败。
- [ ] 每分钟/日额度、批量上限、限流、休市/半日及周末行为有实测记录；额度不足保留缺口，不付费、不拼旧价、不超窗补造历史。
- [ ] 完整价格和权重分别出具全名单矩阵；只有两轴都通过才解除B-01/B-02相应日期阻塞。

**验证：** 适配器契约测试＋五日原件/日志人工核对；模拟时钟测试不替代五日记录。

### E02｜完整真实TTM独立验收

**依赖/负责人：** E01/T13；数据核验。对应 ADD §5.3、§12 B-03、§13.4。

**文件/接口：** `docs/acceptance/full-ttm.md`、`tests/integration/test_full_ttm_contract.py`；沿用EarningsBatch和Snapshot，不新增替代公式。

- [ ] 对同一合格D的全部证券逐条核对最新四季、GAAP稀释口径、股类/ADR、币种、拆股和180日政策，零权重也无缺失。
- [ ] 共享发行人的原件可以复用，证券资格逐条成立；所有新鲜度复核满足strict政策且未超截止。
- [ ] 完整TTM资格、贡献和PE可由归档输入复算；行业加总一致，真实矩阵每行有证据。
- [ ] FY1不完整不阻止TTM通过；任何TTM行不合格则保持partial，本任务不得done，不以接近供应商PE为验收依据。

**验证：** 全名单原件审计＋生产CLI复算＋契约测试，报告快照ID和独立TTM结论。

### E03｜完整FY1来源契约与数据验收

**依赖/负责人：** E01/T13；数据核验。对应 ADD §12 B-04、§13.5。

**文件/接口：** `src/nasdaq100_pe/adapters/forecast.py`、`tests/adapters/test_forecast.py`、`docs/acceptance/full-fy1.md`；输出EarningsBatch。

- [ ] 先覆盖不同财年、负预测、多股类、ADR样本，逐条证明下一财年结束日、normalized EPS mean、单位、币种、股类和合法可用获取路径；样本失败不盲目扩到全篮子。
- [ ] 正式完整输入覆盖每只证券，满足daily获取政策；周度拼接不能用于strict。修订>30日无效，未知修订但新获取允许并保留质量标记。
- [ ] 负EPS保留；零EPS有效；forwardPE、NTM、当前财年或未证明normalized的字段均不可代替FY1。
- [ ] 每行有原件和字段定位，完整指标可复算；找不到合格免费来源时任务blocked、完整FY1未完成，引用Forward卡片继续工作。

**验证：** 代表样本契约测试→全名单审计→生产CLI复算，三个阶段分别留结论，不承诺零预算一定完成。

### E04｜无人值守调度、发布队列及真实恢复验收

**依赖/负责人：** T14/E01；后端/运维。对应 ADD §7—8、§12 B-06、§13.2。

**文件/接口：** `src/nasdaq100_pe/scheduler/slots.py`、`scheduler/queue.py`、`scheduler/worker.py`、`config/launchd/`、`tests/scheduler/`、`docs/acceptance/unattended.md`；`scheduler_tick(now: datetime) -> TickReport`，CLI `scheduler tick`、`collect --date --method`。

- [ ] launchd每小时00/15/30/45 tick；实际收盘后90分钟/3小时/6小时和次日00:15/06:15/11:15槽均有测试，纽约次日12:00截止。日历未知/过期停止生成新日期。
- [ ] 休眠恢复只处理最近一个到期槽，记录真实启动时间；超窗missed_window，不用当前盈利补历史。每目标日/模式/方法单写锁和租约，孤立任务恢复核对进程。
- [ ] 采集和发布队列独立；采集两指标完整停止采集重试，但发布失败继续15/60/180分钟、之后每6小时退避，复用归档。状态发布成功不算快照发布成功。
- [ ] CAS按序列/目标日/revision_seq防止旧任务回退；superseded_no_op有日志，手工回滚单独审计；本机默认自动发布、公开默认关闭。
- [ ] 服务Agent与采集Agent独立，首次无release可启动，退出后重启，重新登录恢复；机器关机/退出登录期间不承诺服务。
- [ ] 每日备份实际执行并验证恢复；状态明确最近尝试、成功、每类完整日期、失败/逾期。超日历范围显示更新时效未知。
- [ ] 连续5个交易日真实运行，附休眠、重启、真实退出/登录、锁过期、存储/发布故障记录；每种故障都证明没有伪造历史或损坏旧版本。仅短时Agent触发不通过。

**验证：** `python -m pytest tests/scheduler -q`＋真实五日运行和故障演练报告。

### E05｜可选公开包及公网发布

**依赖/负责人：** T14＋用户另行选择公网扩展；后端/运维。对应 ADD §8.2、§10、§12.2 N-01/N-02。

**文件/接口：** `src/nasdaq100_pe/publisher/public.py`、`config/public-policy.json`、`tests/publisher/test_public.py`、`docs/acceptance/public-release.md`；`build_public(snapshot_id: str, policy: PublicPolicy) -> Release`，CLI `build-public --snapshot --policy`。

- [ ] local_processing/public_display/public_derived_metrics/public_download分别有字段范围、allowed/denied/unverified、依据和有效期；过期或未知不视作allowed。
- [ ] 页面、浏览器可取JSON、CSV和其他导出统一按各自权限过滤；隐藏按钮不能代替移除字段。redacted_fields明确，缺复算输入时reproducible=false。
- [ ] 独立public目录/指针/队列，权限拒绝退出5并blocked_policy，不影响本机；不从local包直接部署。
- [ ] 公网无写/管理入口，扫描静态文件、source map和错误包无原件/秘密；云账号/免费额度/数据权限在实施时核实。
- [ ] 实际部署后HTTP、版本一致、回滚及权限检查通过才认定公开发布；权限不足只能明确合成演示，报告“公开真实数据未完成”。

**验证：** `python -m pytest tests/publisher/test_public.py -q`＋部署后外部读取核验，保留独立公网验收结论。

## 7. 需求追踪与首版发布判定

| ADD要求 | 任务 | 验收证据 |
|---|---|---|
| §0.1—0.2 引用契约、手工录入、独立主页面 | T01—T06 | schema/CLI测试、真实原件、页面/导出核对 |
| §0.3、§13.3—13.6 研究/子集/周度/模式隔离 | T07—T11 | 模式与日期边界、子集数值及UI测试 |
| §4 数据契约、证据、导入导出 | T01/T02/T04/T07/T10 | 非法输入、幂等、复算和CSV测试 |
| §5 身份/权重/价格/盈利 | T07/T09/T12/T13；E01—E03 | 资格测试、覆盖矩阵、原件审计 |
| §6 公式、行业、市值、派生 | T08/T09 | SRD合成数值与反例测试 |
| §7.3—7.4 归档/更正/原子发布/恢复 | T02/T03/T10/T14 | 崩溃注入、CAS、复算、备份恢复 |
| §7.1—7.2、§13.2 自动采集与独立重试 | E04 | 槽位测试和五日真实运行 |
| §8.1/8.3 回环/敏感信息/导入安全 | T01/T03/T04/T05/T14 | 真实HTTP、XSS/穿越/秘密扫描 |
| §8.2 公网 | E05 | 独立权限矩阵和公网验收 |
| §9 交互、明细、历史及异常 | T05/T11/T14 | 组件/E2E/视口/键盘与性能证据 |
| §10 CLI和退出码 | T01/T04/T10/T12；E04/E05 | 各操作JSON状态与退出码测试 |
| §11 验证/性能/追踪 | T14 | 完整首版验收报告 |
| §12 旧阻塞与验收轴 | T06/T12/T13/T14；E01—E05 | 各轴分别判定，旧报告不改写 |

保留但不在本轮任务内的增强：D−1事件全覆盖估算、历史回填、官方指数来源接入、经独立验证的外币/其他盈利路径。对应入口默认关闭；不通过重命名研究模式、替换权重或降口径隐式启用。

首版发布要求T01—T14完成，其中T06必须取得两类真实引用，T12/T13允许按明确缺口完成软件与核验报告。完整真实TTM/FY1的未完成不阻塞发布；缺真实引用、回环隔离失败、公式/模式错误、证据不可追溯或秘密泄露则阻止发布。

计划自查：已逐节映射ADD；§0覆盖的旧公网/自动日更/全量数据前置条件已移出首版；五类Review Focus均有归属测试。本文是任务基线，所有任务尚未执行，不能用本表代替任何软件或真实数据验收。
