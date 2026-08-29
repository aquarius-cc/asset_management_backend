#!/bin/bash
# backup_status.sh - 备份可观测状态写入（N-2 / 对抗设计）
# 由 backup.sh / redis_backup.sh / media_backup.sh 的 EXIT trap 调用。
# 契约：原子发布（同卷 tmp→mv）、非 root 可读（644）、写入失败不反噬业务。

backtrack () {
  echo "# BACKUP STATUS TRACE" >&2
  echo "# Status: $(date -Iseconds) | RC: $1 | File: ${BACKUP_STATUS_DIR:-/data/backup_status}/backup_status.prom" >&2
}

backup_status_write () {
  local _rc="${1:-1}"
  local _dir="${BACKUP_STATUS_DIR:-/data/backup_status}"
  # 最佳努力：任何异常静默吞掉，备份业务流程不受影响
  {
    mkdir -p "$_dir" 2>/dev/null || true
    umask 022
    chmod 755 "$_dir" 2>/dev/null || true
    local f="$_dir/backup_status.prom"
    local now old old_fail old_ts new_fail new_ts tmp
    now=$(date +%s 2>/dev/null || echo 0)
    old_ts=0; old_fail=0
    if [ -f "$f" ]; then
      old_ts=$(awk '$1=="backup_last_success_timestamp"{v=$2} END{print v+0}' "$f" 2>/dev/null || echo 0)
      old_fail=$(awk '$1=="backup_failures_total"{v=$2} END{print v+0}' "$f" 2>/dev/null || echo 0)
    fi
    case "$old_ts" in ''|*[!0-9]*) old_ts=0;; esac
    case "$old_fail" in ''|*[!0-9]*) old_fail=0;; esac
    if [ "$_rc" -eq 0 ]; then
      new_ts="$now"; new_fail="$old_fail"
    else
      new_ts="$old_ts"; new_fail=$((old_fail + 1))
    fi
    # flock 保护：同容器三个脚本可能重叠（虽不重叠，但防御性串行）
    tmp="$_dir/.backup_status.prom.tmp.$$"
    {
      echo "# HELP backup_last_success_timestamp Last successful daily backup run (unix timestamp)."
      echo "# TYPE backup_last_success_timestamp gauge"
      echo "backup_last_success_timestamp $new_ts"
      echo "# HELP backup_failures_total Total failed daily backup runs (monotonic since volume creation)."
      echo "# TYPE backup_failures_total counter"
      echo "backup_failures_total $new_fail"
    } > "$tmp"
    chmod 644 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$f" 2>/dev/null || true
    chmod 644 "$f" 2>/dev/null || true
  } 2>/dev/null || true
  return 0
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  echo "Usage: source $0; backup_status_write [exit_code]" >&2
  exit 1
fi
