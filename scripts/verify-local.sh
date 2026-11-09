#!/usr/bin/env bash
# 一键本机验收：后端测试 → 前端单测 → 构建 → 浏览器 E2E。任一步失败即退出非 0。
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
echo "== backend =="; $PY -m pytest tests -q
echo "== web unit =="; npm --prefix apps/web run test -- --run
echo "== web build =="; npm --prefix apps/web run build
echo "== web e2e =="; npm --prefix apps/web run test:e2e
echo "ALL CHECKS PASSED (本机软件验收；不代表真实数据验收，见 docs/acceptance/release-v1.md)"
