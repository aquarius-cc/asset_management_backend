#!/bin/bash
# backup_verify.sh - 每周验证备份文件可读性
# 依据: 08-数据备份恢复方案.md §4 "备份文件可读性: pg_restore -l 无报错"
set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
FAIL_COUNT=0
TOTAL_COUNT=0

for dump_file in "$BACKUP_DIR"/full_*.dump; do
    [ -f "$dump_file" ] || continue
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    if pg_restore -l "$dump_file" > /dev/null 2>&1; then
        echo "✅ $(basename "$dump_file") — 可读"
    else
        echo "❌ $(basename "$dump_file") — 不可读"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo ""
echo "共 $TOTAL_COUNT 个备份文件, $FAIL_COUNT 个不可读"

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "❌ 备份可读性检查失败"
    exit 1
fi
echo "✅ 备份可读性检查通过"
