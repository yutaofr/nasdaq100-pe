# 2026-11-09 real input acceptance: QQQ proxy basket

## Scope and decision

The observation target is **2026-11-05** (`W = D`). This is a local, private **research** snapshot of the QQQ equity holdings proxy, not an official Nasdaq-100 index valuation. The holdings were retrieved on 2026-11-09, after the strict next-day cutoff. No complete TTM or FY1 PE is qualified. The final research input contains all 101 equity identities and weights plus one verified AAPL closing price and four-quarter GAAP EPS. The engine retains null full-basket PE and identifies the other 100 missing TTM securities.

## Primary evidence and reconciliation

| Evidence | Observation | Local record |
|---|---|---|
| [Invesco QQQ holdings JSON](https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/fund?idType=ticker&interval=monthly&productType=ETF) | `effectiveDate = 2026-11-05`; `totalNumberOfHoldings = 106`; SHA-256 `ee6dbfc062936a5e40dac73b066a84e634b8800858c7c48d9ef76f6bd9384824` | `/Users/weizhang/ndx-pe-data/inputs/evidence/invesco-qqq-holdings-ee6dbfc062936a5e40dac73b066a84e634b8800858c7c48d9ef76f6bd9384824.json` |
| [SEC ticker to CIK map](https://www.sec.gov/files/company_tickers.json) | 101 securities resolve to 100 CIKs; GOOG and GOOGL share one CIK. The ticker map was retrieved on 2026-11-09 and does not establish historical share-class validity. | `sec-company-tickers-<sha256>.json` under the evidence directory |
| [Nasdaq historical data](https://www.nasdaq.com/market-activity/quotes/historical) | 101/101 dated 2026-11-05 `Close/Last` candidate rows were retrieved via the Nasdaq-hosted JSON. The response does not identify a raw split basis, official NOCP, or consolidated feed. These generic candidate rows were **not** promoted to qualified prices. | `nasdaq-historical/<ticker>-2026-11-05-<sha256>.json` under the evidence directory |
| [Nasdaq Historical NOCP for AAPL](https://www.nasdaq.com/market-activity/stocks/aapl/historical-nocp) | Page JavaScript calls `GET /api/company/AAPL/historical-nocp?timeframe=d5`; the JSON has `Trade Date = 11/05/2026`, `Nasdaq Closing Price = $344.17`. This is a distinct official-close source and matches the generic `Close/Last` value. SHA-256 `3d3f834b3618b1aff71697863b635cc968e875ff3b100ca34087a81943892624`. | `nasdaq-aapl-nocp-d5-3d3f834b3618b1aff71697863b635cc968e875ff3b100ca34087a81943892624.json` under the evidence directory |
| [SEC companyfacts API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 100/100 current issuer responses; fetched after the target date. Every response is content-addressed and indexed by CIK. SEC fact presence alone does not establish a target-date-valid, class-matched, split-matched TTM EPS. | `/Users/weizhang/ndx-pe-data/store/sec_cache/` metadata and `/Users/weizhang/ndx-pe-data/store/raw/<content_sha256>` bytes |

The 106 holdings are 98 common stocks, 3 ADRs, and 5 non-equity rows. The 101 equity weights sum to `0.99831932`; known non-equity weights, including the cancelling future and synthetic-cash positions, sum to `0.00168071`; the displayed total is `1.00000003`, within six-decimal percentage rounding. One pending-dividend cash row has no weight. The proxy normalizes the **full equity basket**; it does not treat the unknown non-equity value as zero. ADR ratios remain unknown.

## Full-basket field screening

The local [101-row matrix](/Users/weizhang/ndx-pe-data/inputs/research-2026-11-05/coverage-matrix.csv) records, for each symbol, the raw proxy weight, candidate price and its response hash, SEC CIK and companyfacts hash, TTM screen, FY1 status, and blockers. Its AAPL row records the later manual NOCP and Q4 adjudication. The final [partial research input](/Users/weizhang/ndx-pe-data/inputs/research-2026-11-05/research-input-aapl-partial.json) is the exact basket submitted to the calculation pipeline; the original [basket-only input](/Users/weizhang/ndx-pe-data/inputs/research-2026-11-05/research-input.json) remains as earlier audit evidence. The [summary](/Users/weizhang/ndx-pe-data/inputs/research-2026-11-05/summary.json) records final aggregate counts.

| Field | Retrieved candidate | Qualified for the 2026-11-05 PE computation |
|---|---:|---:|
| Equity identity and QQQ proxy weight | 101/101 | 101/101 as a private research proxy basket |
| Dated Nasdaq `Close/Last` | 101/101 generic candidates; one separate NOCP record | 1/101, AAPL, from the NOCP endpoint and split review |
| SEC companyfacts and company Q4 release | 100/100 SEC issuers; one Apple Q4 8-K supplement | 1/101 TTM EPS, AAPL; the other 100 remain unqualified |
| FY1 normalized consensus mean with explicit next fiscal year end | 0/101 | 0/101 |

Initial SEC-only four-quarter screening: 94 securities lacked a directly available Q4 quarter, four lacked the selected US-GAAP diluted-EPS label, and two lacked another required quarter. Apple's Q4 was subsequently resolved from its official 8-K exhibit, leaving 93 of those Q4 gaps. The lone initially direct four-quarter candidate, **HON**, is not eligible because its selected 2025 Q4 fact comes from accession `0000773840-26-000013` (10-K filed 2026-02-17), before a [1-for-2 reverse split effective 2026-06-29](https://investor.honeywell.com/reverse-stock-split). Its later selected Q2 fact comes from accession `0000773840-26-000124` (10-Q filed 2026-07-23), which [states that presented per-share figures were retrospectively adjusted for the split](https://investor.honeywell.com/static-files/9cf1562f-23df-4f0a-babe-ad6e2c052e78). The selected Q3 fact is from accession `0000773840-26-000143` (10-Q filed 2026-10-22). Summing those facts as if they share one basis would be unsound; the apparent 21.02 USD/share is **screening output only**, not a TTM EPS input. The company also spun off its aerospace business on the split date, so a simple multiplier would not settle the accounting-scope question.

There is no verified FY1 source with a next-year end, normalized mean EPS and revision date for all securities. No website's aggregate PE or raw Yahoo chart close is an input. AAPL alone contributes a known `0.002270022335743066...` to the QQQ proxy's TTM earnings yield (0.227002233574... percentage points); the unobserved remainder is **not** treated as zero. Both full PE values remain null.

### Focused AAPL quarter and price check

Apple's [November 2, 2026 Q4 release](https://www.apple.com/newsroom/2026/11/apple-reports-fourth-quarter-results/) reports diluted EPS of **$2.10** for the quarter ended September 26. The release is also in SEC [8-K accession `0000320193-26-000024`](https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/0000320193-26-000024-index.html), before the November 5 target date. The Apple release HTML was archived locally as `apple-fy2026-q4-fa272456c3df64c93c05f5437cbc7f4c61503d76fcbbe11330cfe8a759033dd9.html`.

SEC companyfacts has FY2026 direct-quarter diluted EPS of **$2.84** for Q1 (10-Q accession `0000320193-26-000006`), **$2.01** for Q2 (`0000320193-26-000013`), and **$2.02** for Q3 (`0000320193-26-000020`). Those three plus the reported Q4 make **$8.97** as a sum of four reported quarters. The [2026 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/aapl-20260926.htm), accession `0000320193-26-000026`, reports **$8.98** diluted EPS for the full fiscal year. The $0.01 difference is a real distinction between the annual and rounded-quarter paths; neither is silently substituted for the other. Apple's [investor FAQ](https://investor.apple.com/investor-relations/faq/default.aspx) lists its last stock split in 2020, so no split is identified across these four quarters and the target date.

The generic `Close/Last` remains an unqualified price source. The [separate Nasdaq Historical NOCP page](https://www.nasdaq.com/market-activity/stocks/aapl/historical-nocp) calls NOCP the Nasdaq market-specific official close. Its loaded component JavaScript calls `https://api.nasdaq.com/api/company/AAPL/historical-nocp?timeframe=d5`; the archived response explicitly labels the 2026-11-05 **$344.17** row as `Nasdaq Closing Price`. Nasdaq's [listing FAQ](https://listingcenter.nasdaq.com/Material_Search.aspx?cid=71&mcd=lq&sub_cid=118%2C98%2C96%2C99%2C100%2C94) distinguishes NOCP from a consolidated closing bid. Apple's split history has no event since 2020, so the 2026 quarterly EPS and 2026-11-05 NOCP are on the same known share basis. The [manual Q4 supplement](/Users/weizhang/ndx-pe-data/inputs/research-2026-11-05/apple-q4-supplement.json) retains the company release hash and SEC 8-K accession. The independently computed **AAPL security PE is 344.17 / 8.97 = 38.3690...**; it is a one-security result, never a Nasdaq-100 or full-QQQ PE.

## Reproduction and release gate

The collector is `scripts/collect_real_research.py`. It archives the official raw holdings, candidate prices and SEC facts, and produces the initial matrix and basket input. It uses a reachable Git-configured contact for SEC Fair Access and a 0.25-second minimum interval. AAPL's NOCP, Apple Q4 evidence and supplement were then adjudicated separately in the final input and matrix. The normal path is `validate`, `import`, `recompute`, and research release build with `data_mode=real`; a research release must be verified over local HTTP before promotion. The reference-only published release pointer remains unchanged.

The first archived research snapshot (`b0afcb686bc367f8fcd2`) exposed a reproducibility bug: the initial computation used source-list order, while the archived canonical input sorted list entries. That immutable snapshot and its releases remain in the archive as audit history, but are excluded from the current research release. After fixing initial computation to use the archived canonical input, the basket-only revision 2 and AAPL partial revision 3 were independently recomputed. The current research release contains only revision 3:

| Gate | Observed result |
|---|---|
| `validate` | `ok=true`, `basket_qualified=true`, 101 equity rows |
| `import` | snapshot `e4c9c407a30be4aae02e`, input hash `90c426bb4c0f7e8e4227b8d412f68ab86035c3b847d4b8c58a9a9947c087f6ab` |
| `recompute` | `identical=true`, `errors=[]` |
| Engine result | TTM `partial`, 1/101 securities, `8.7098504714904245...%` of known proxy equity weight; AAPL contribution `0.227002233574...` percentage points; full TTM `pe=null`; FY1 `unavailable`, `pe=null` |
| Research release | `6cc1f9c51b76ed68`, contains only the reproducible revision-3 snapshot; all release files verified through local HTTP before promotion |
| Reference release | Pointer remains `34f3fd1c81aadc38` |

The local research release is a working basket-and-gap chain through the first-principles engine with one primary-source TTM contribution. It is **not** a successful full real-data PE calculation. The other 100 securities require verified price and four-quarter earnings evidence; full FY1 normalized consensus remains unavailable.
