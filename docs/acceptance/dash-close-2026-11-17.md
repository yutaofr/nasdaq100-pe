# DASH 收盘价缺口排查（2026-11-17）

状态：软件补录路径已修复；真实 DASH 收盘价仍缺失，未修改或发布研究快照。

- 目标价格日为 2026-11-13，索引位于 `~/ndx-pe-data/inputs/research-2026-11-13/nocp-index.json`，DASH 记录为 HTTP_403。
- 使用采集器相同 URL 与请求头在本机单次请求，确认 HTTP 403。没有重试或绕过拒绝。
- 已归档 `DASH-d5-55b56e6c9485d5a825228ac6805fa9fec4208b3d8b4b47df64dbe4180f805b9d.json` 的内容是 data=null、业务错误码 1002、Nasdaq Historical NOCP only for Nasdaq Symbols。它不含任何价格。该回复不能证明 DASH 实际未在 Nasdaq 上市，只能证明服务未提供该证券的 NOCP。
- Nasdaq 的 DASH Historical NOCP 网页也显示 Data is currently not available。DoorDash 投资者关系页面的本机访问返回拒绝页面。未获得符合价格契约的替代原件。

修改：增加保存响应补录入口，验证证券、日期、价格表头和正数价格，归档原件与哈希，保留补录前失败信息；将业务错误 1002 明确标记为 NOCP_UNAVAILABLE_FOR_SYMBOL；修复清除非法字符可能将负数或畸形文本变成正价格的问题。删除“换网络重跑即可恢复”的保证。

后续需要包含 DASH 和 2026-11-13 的真实 NOCP 响应，或另行核验满足项目 raw / regular close 契约的其他来源。合成测试数据只用于回归测试，不能作为真实价格证据。
