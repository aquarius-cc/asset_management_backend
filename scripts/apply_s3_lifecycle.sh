#!/bin/bash
set -euo pipefail

# S3 生命周期策略应用脚本 — 一次性基础设施操作 (BF-003 收口)
# 用途: 为备份 bucket 配置 30d→STANDARD_IA 过渡 + 90d 删除对象。
# 所需 IAM 权限:
#   s3:PutLifecycleConfiguration   (应用)
#   s3:GetLifecycleConfiguration   (应用前比对 / 应用后验收)
# 安全约束 (SC-1/AR-4): 凭据与 bucket 名一律经环境变量注入 (AWS CLI 默认链), 禁止落盘仓库。
# 说明: 三份备份脚本上传时即 STANDARD_IA (backup.sh:59 / redis_backup.sh:64 / media_backup.sh:52),
#       故 30d→IA 规则仅防御历史 STANDARD 对象; 90d 删除为实质保留策略, 与本地 30 天保留分档。

S3_BUCKET="${S3_BUCKET:-}"
if [ -z "$S3_BUCKET" ]; then
  echo "[ERROR] 缺少环境变量 S3_BUCKET (目标 bucket 名)" >&2
  echo "用法: S3_BUCKET=<bucket> bash $(basename "$0")" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIFECYCLE_FILE="$SCRIPT_DIR/s3_lifecycle.json"

echo "== 当前位置 (应用前比对) =="
if aws s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET" 2>/dev/null; then
  echo "(存在现有生命周期配置, 见上)"
else
  echo "(无现有生命周期配置)"
fi

echo "== 应用 $LIFECYCLE_FILE =="
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$S3_BUCKET" \
  --lifecycle-configuration "file://$LIFECYCLE_FILE"

echo "== 应用后回读 (人工验收) =="
aws s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET"