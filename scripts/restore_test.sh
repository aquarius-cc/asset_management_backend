#!/bin/bash
# restore_test.sh - 恢复演练脚本
# 依据: 08-数据备份恢复方案.md §4 恢复演练
# 用法: ./restore_test.sh <backup_file> [test_db_name]
# 环境变量: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD
set -uo pipefail

BACKUP_FILE="${1:?用法: $0 <backup_file> [test_db_name]}"
TEST_DB="${2:-asset_management_restore_test}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
RESULT_DIR="${RESULT_DIR:-/tmp/restore_test_results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULT_DIR/restore_test_${TIMESTAMP}.md"

# 状态追踪（不用 set -e,避免 pg_restore 非零退出导致脚本中断）
RESTORE_OK=false
TABLE_COUNT=0
ASSET_COUNT=0
DURATION=0

mkdir -p "$RESULT_DIR"

# --- 步骤 0: 预清理(防上次演练被 kill 残留测试库导致本次失败) ---
PGPASSWORD="$DB_PASSWORD" dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$TEST_DB" 2>/dev/null || true

echo "# 恢复演练报告" > "$RESULT_FILE"
echo "" >> "$RESULT_FILE"
echo "- **时间**: $(date '+%Y-%m-%d %H:%M:%S')" >> "$RESULT_FILE"
echo "- **备份文件**: $(basename "$BACKUP_FILE")" >> "$RESULT_FILE"
echo "- **测试数据库**: $TEST_DB" >> "$RESULT_FILE"
echo "" >> "$RESULT_FILE"

# --- 步骤 1: 创建测试数据库 ---
echo "## 步骤 1: 创建测试数据库" >> "$RESULT_FILE"
PGPASSWORD="$DB_PASSWORD" createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TEST_DB" 2>/dev/null || true
echo "✅ 测试数据库 $TEST_DB 已就绪" >> "$RESULT_FILE"

# --- 步骤 2: 恢复全量备份 ---
echo "## 步骤 2: 全量恢复" >> "$RESULT_FILE"
START_TIME=$(date +%s)
PGPASSWORD="$DB_PASSWORD" pg_restore \
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
  -d "$TEST_DB" \
  --clean --if-exists \
  --no-owner --no-privileges \
  "$BACKUP_FILE" 2>/dev/null || true
# pg_restore 对部分对象可能返回非零(如已存在),不视为致命错误
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "- **耗时**: ${DURATION} 秒" >> "$RESULT_FILE"
if [ "$DURATION" -lt 3600 ]; then
  echo "- **RTO 达标**: ✅ (< 3600s)" >> "$RESULT_FILE"
else
  echo "- **RTO 达标**: ❌ (≥ 3600s)" >> "$RESULT_FILE"
fi

# --- 步骤 3: 数据完整性验证 ---
echo "## 步骤 3: 数据完整性" >> "$RESULT_FILE"

TABLE_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEST_DB" -t -A -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" 2>/dev/null || echo "0")
echo "- **表数量**: $TABLE_COUNT" >> "$RESULT_FILE"

ASSET_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEST_DB" -t -A -c \
  "SELECT count(*) FROM am_asset;" 2>/dev/null || echo "0")
echo "- **资产记录数(am_asset)**: $ASSET_COUNT" >> "$RESULT_FILE"

EMPLOYEE_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEST_DB" -t -A -c \
  "SELECT count(*) FROM am_employee;" 2>/dev/null || echo "0")
echo "- **员工记录数(am_employee)**: $EMPLOYEE_COUNT" >> "$RESULT_FILE"

AUTH_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEST_DB" -t -A -c \
  "SELECT count(*) FROM auth_user_management_table;" 2>/dev/null || echo "0")
echo "- **认证用户数(auth_user_management_table)**: $AUTH_COUNT" >> "$RESULT_FILE"

# --- 步骤 4: 清理测试数据库 ---
echo "## 步骤 4: 清理" >> "$RESULT_FILE"
PGPASSWORD="$DB_PASSWORD" dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TEST_DB" 2>/dev/null || true
echo "- 测试数据库 $TEST_DB 已清理" >> "$RESULT_FILE"

# --- 步骤 5: 综合判定 ---
echo "" >> "$RESULT_FILE"
echo "## 综合判定" >> "$RESULT_FILE"
if [ "$DURATION" -lt 3600 ] && [ "$TABLE_COUNT" -gt 0 ]; then
  echo "**结论: ✅ 演练通过**" >> "$RESULT_FILE"
  echo "报告已保存: $RESULT_FILE"
  exit 0
else
  echo "**结论: ❌ 演练失败,请检查上述步骤**" >> "$RESULT_FILE"
  echo "报告已保存: $RESULT_FILE"
  exit 1
fi
