#!/usr/bin/env bash
# ============================================================
# QReward — Full Regression Test
#
# Usage: bash .harness/scripts/regression.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

OVERALL_STATUS="PASS"
REPORT=""

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

append_report() { REPORT="${REPORT}$1\n"; }

echo "============================================================"
echo "  QReward — Full Regression Test"
echo "  $(timestamp)"
echo "============================================================"
echo ""

append_report "## 回归测试报告"
append_report ""
append_report "### 执行时间: $(timestamp)"
append_report ""

# ── Dimension 1: Lint ────────────────────────────────────────
echo "── Dimension 1: Lint check ──"
LINT_STATUS="✅"
LINT_DETAIL=""
if $LINT_CMD 2>/dev/null; then
    LINT_DETAIL="No errors"
    echo -e "${GREEN}✅ Lint: PASS${NC}"
else
    LINT_STATUS="⚠️"
    LINT_DETAIL="Lint errors found (non-blocking)"
    echo -e "${YELLOW}⚠️  Lint: WARNING${NC}"
fi
echo ""

# ── Dimension 2: Unit tests ─────────────────────────────────
echo "── Dimension 2: Unit tests ──"
UT_STATUS="✅"
UT_DETAIL=""
UT_OUTPUT=$(pytest tests/ -v --tb=short 2>&1) || true
UT_PASSED=$(echo "$UT_OUTPUT" | grep -oE '[0-9]+ passed' | head -1 || echo "0 passed")
UT_FAILED=$(echo "$UT_OUTPUT" | grep -oE '[0-9]+ failed' | head -1 || echo "")

if [ -n "$UT_FAILED" ]; then
    UT_STATUS="❌"
    UT_DETAIL="$UT_PASSED, $UT_FAILED"
    OVERALL_STATUS="FAIL"
    echo -e "${RED}❌ Unit tests: FAIL${NC} — $UT_DETAIL"
else
    UT_DETAIL="$UT_PASSED"
    echo -e "${GREEN}✅ Unit tests: PASS${NC} — $UT_DETAIL"
fi
echo ""

# ── Dimension 3: Coverage ───────────────────────────────────
echo "── Dimension 3: Coverage ──"
COV_STATUS="✅"
COV_DETAIL=""
COV_OUTPUT=$(pytest --cov="$SRC_DIR" --cov-report=term-missing 2>&1) || true
TOTAL_COV=$(echo "$COV_OUTPUT" | grep "^TOTAL" | awk '{print $NF}' | tr -d '%' || echo "0")

if [ -n "$TOTAL_COV" ] && [ "$TOTAL_COV" -ge 80 ]; then
    COV_DETAIL="Total coverage ${TOTAL_COV}%"
    echo -e "${GREEN}✅ Coverage: PASS${NC} — ${TOTAL_COV}%"
else
    COV_STATUS="⚠️"
    COV_DETAIL="Total coverage ${TOTAL_COV}% (< 80%)"
    echo -e "${YELLOW}⚠️  Coverage: WARNING${NC} — ${TOTAL_COV}%"
fi
echo ""

# ── Report ───────────────────────────────────────────────────
append_report "| 维度 | 状态 | 详情 |"
append_report "|------|------|------|"
append_report "| Lint | $LINT_STATUS | $LINT_DETAIL |"
append_report "| 单元测试 | $UT_STATUS | $UT_DETAIL |"
append_report "| 覆盖率 | $COV_STATUS | $COV_DETAIL |"
append_report ""
append_report "### 总体判定: $OVERALL_STATUS"

# ── Summary ──────────────────────────────────────────────────
echo "============================================================"
echo "  Regression Summary"
echo "============================================================"
echo -e "  Lint:        $LINT_STATUS $LINT_DETAIL"
echo -e "  Unit tests:  $UT_STATUS $UT_DETAIL"
echo -e "  Coverage:    $COV_STATUS $COV_DETAIL"
echo ""

if [ "$OVERALL_STATUS" = "FAIL" ]; then
    echo -e "${RED}REGRESSION FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}REGRESSION PASSED${NC}"
    exit 0
fi
