# Restore calculated PE home — implementation plan

**Goal:** Make the SRD §3 weight × earnings-yield calculation the dashboard's default path and keep published PE as an explicitly labeled external reference.

**Architecture:** Keep the existing independent research and published release providers. Route `/`, `#/`, and `#/research` to the research dashboard; route `#/reference` to published source observations. The research empty state explains the formula and completeness gates without displaying a published PE as a fallback.

**Scope:** `apps/web/**`, `README.md`, and `docs/ADD.md`. No data-engine or release-format changes. The 2026-11-08 ADD decision to put published PE on the home page is superseded by the user's 2026-11-09 correction; its historical record remains in place.

## Steps

- [x] Add a failing front-end regression for default route with a published PE and no research release: no published PE value or card may appear, and formula/completeness guidance must appear.
- [x] Add route assertions for `#/`, `#/research`, and `#/reference`, including external-reference navigation and page heading.
- [x] Change routing, labels, and research empty/loading states; keep missing earnings distinct from zero and retain negative earnings behavior in existing result components.
- [x] Update e2e and performance routes; run the full front-end unit suite, build, and appropriate e2e checks.
- [x] Revise README and annotate ADD's historical home-page decision with the new precedence. Record test results and outstanding real-data limitations below.

## Acceptance record

2026-11-09: The new default-route unit test failed against the old published-first route and passed after implementation. A separate partial-snapshot status assertion failed before the status copy was added and then passed. `npm test -- --run`: 41/41 passed. `npm run build`: passed (TypeScript and Vite). `npm run test:e2e -- --reporter=list`: 33/33 passed with the synthetic fixture's four-quarter evidence restored by the concurrent validation work. `git diff --check`: passed. Performance test route now targets `/`; a new performance measurement was not run because it writes an acceptance artifact outside this front-end scope.

These tests establish routing and display behavior with controlled releases. They do not establish complete real TTM or FY1 coverage, market accuracy, or a numeric self-calculated PE in the live release.

Live spot-check of `127.0.0.1:8765` after real research release `12148507a61f5c92`: the release contains 101 securities; TTM and FY1 are independently `unavailable`, each with 101 missing securities and null portfolio yield/PE. Chrome at 390px rendered 101 constituent rows, both main PE cards as “— 无有效盈利”, both status lines as “未形成完整自算 PE”, and no published-source card on `/`. It labeled D as the target price date and had no horizontal overflow. `/#/reference` displayed the separate Stock Analysis observations under “外部估值对照（来源公布，非本站自算）”; the research constituent table was absent there. This is a display and state check, not validation of price or EPS coverage.

Later live release `6cc1f9c51b76ed68` superseded that observation during the same session: 101 securities, TTM `partial` with 100 missing, FY1 `unavailable` with 101 missing; both full portfolio PE values remain null. A fresh Chrome 390px check showed 101 rows, TTM “部分覆盖；未形成完整自算 PE” with “— 盈利未完整”, FY1 “不可用；未形成完整自算 PE” with “— 无有效盈利”, zero source-published cards on `/`, and no horizontal overflow. The front-end unit suite, build, and 33 e2e tests were rerun after the validation changes and passed.
