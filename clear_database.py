#!/usr/bin/env python
"""
数据库清空脚本 - 资产管理系统

【用途】
清空所有业务数据表，保留 Django 系统表（auth_permission、django_migrations 等）。
用于功能测试前的数据重置。

【安全设计】
1. 必须先备份才能执行清空
2. 白名单机制：只清空已知业务表，未知表不碰
3. 事务包裹：单表事务，失败即停
4. 执行前二次确认
5. 执行后自动验证

【回退方案】
- 备份文件位于 backups/ 目录，可通过 MySQL 恢复
- 保留 django_migrations 表，不影响迁移状态
"""

import os
import sys
import django

# 设置 Django 环境
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "apps"))

django.setup()

from datetime import datetime
from pathlib import Path
from typing import List

from django.db import connection, transaction


# =============================================================================
# 配置区
# =============================================================================

# 允许清空的业务表白名单（按依赖顺序排列，先清子表）
ALLOWED_TABLES: List[str] = [
    # 审计日志（无强外键依赖）
    "am_asset_operation_log",
    # 未登记资产
    "am_unregistered_asset",
    # 硬盘序列号
    "am_hard_disk_sn",
    # 已报废
    "am_waste_asset",
    # 待报废
    "am_damaged_asset",
    # 回收
    "am_recycle_asset",
    # 出库
    "am_out_asset",
    # 资产
    "am_asset",
    # 合同
    "am_contract",
    # 资产类型
    "am_asset_type",
    # 仓库
    "am_storage",
    # 员工
    "user_database_table",
    # 部门
    "department_database_table",
    # 认证用户
    "auth_user_management_table",
    # Token 黑名单
    "token_blacklist_outstandingtoken",
    "token_blacklist_blacklistedtoken",
]

# Django 系统表 - 绝对禁止清空
PROTECTED_TABLES: List[str] = [
    "django_migrations",
    "django_content_type",
    "auth_permission",
    "auth_group",
    "auth_group_permissions",
    "auth_user",
    "auth_user_groups",
    "auth_user_user_permissions",
    "django_admin_log",
    "django_session",
]

BACKUP_DIR = Path(__file__).resolve().parent / "backups"


# =============================================================================
# 工具函数
# =============================================================================

def get_db_info() -> dict:
    """获取当前数据库连接信息"""
    db_settings = connection.settings_dict
    return {
        "engine": db_settings.get("ENGINE", ""),
        "name": db_settings.get("NAME", ""),
        "host": db_settings.get("HOST", ""),
        "port": db_settings.get("PORT", ""),
        "user": db_settings.get("USER", ""),
        "password": db_settings.get("PASSWORD", ""),
    }


def list_all_tables() -> List[str]:
    """列出数据库中所有用户表"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        return [row[0] for row in cursor.fetchall()]


def get_table_count(table_name: str) -> int:
    """获取指定表的数据行数"""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        return cursor.fetchone()[0]


def create_backup() -> Path:
    """创建数据库备份（SQL 导出）"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_info = get_db_info()
    db_name = db_info["name"]
    backup_file = BACKUP_DIR / f"backup_{db_name}_{timestamp}.sql"

    # 使用 mysqldump 备份
    import subprocess

    cmd = [
        "mysqldump",
        "-h", db_info["host"] or "localhost",
        "-P", str(db_info["port"] or 3306),
        "-u", db_info["user"] or "root",
        "--single-transaction",
        "--routines",
        "--triggers",
        db_name,
    ]

    # 如果有密码，通过环境变量传递
    env = os.environ.copy()
    password = db_info.get("password")
    if password:
        env["MYSQL_PWD"] = password

    with open(backup_file, "w", encoding="utf-8") as f:
        result = subprocess.run(
            cmd,
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    if result.returncode != 0:
        backup_file.unlink(missing_ok=True)
        raise RuntimeError(f"备份失败: {result.stderr}")

    return backup_file


def clear_table(table_name: str) -> int:
    """
    清空单张表，返回删除的行数

    Args:
        table_name: 表名

    Returns:
        int: 删除的行数

    Raises:
        RuntimeError: 表不在白名单中或清空失败
    """
    if table_name not in ALLOWED_TABLES:
        raise RuntimeError(f"表 '{table_name}' 不在白名单中，禁止清空")

    if table_name in PROTECTED_TABLES:
        raise RuntimeError(f"表 '{table_name}' 是系统保护表，禁止清空")

    count = get_table_count(table_name)

    # 使用独立连接确保 FOREIGN_KEY_CHECKS 状态可靠恢复
    fk_restored = False
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                cursor.execute(f"DELETE FROM `{table_name}`")
                deleted = cursor.rowcount
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                fk_restored = True
    except Exception:
        if not fk_restored:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            except Exception:
                pass
        raise

    return deleted


def verify_cleared() -> dict:
    """验证所有白名单表是否已清空"""
    results = {}
    for table in ALLOWED_TABLES:
        count = get_table_count(table)
        results[table] = count
    return results


def print_summary(results: dict, title: str = "数据汇总") -> None:
    """打印表格数据汇总"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    total = 0
    for table, count in results.items():
        status = "✓ 已清空" if count == 0 else f"✗ {count} 条"
        print(f"  {table:<40} {status}")
        total += count
    print(f"{'-'*60}")
    print(f"  总计: {total} 条数据")
    print(f"{'='*60}\n")


# =============================================================================
# 主流程
# =============================================================================

def main():
    print("=" * 70)
    print("  资产管理系统 - 数据库清空工具")
    print("=" * 70)

    # 1. 环境检查
    db_info = get_db_info()
    print(f"\n【数据库信息】")
    print(f"  数据库: {db_info['name']}")
    print(f"  主机:   {db_info['host']}:{db_info['port']}")
    print(f"  引擎:   {db_info['engine']}")

    # 2. 扫描所有表
    all_tables = list_all_tables()
    print(f"\n【表扫描】发现 {len(all_tables)} 张表")

    # 检查是否有未知表
    known_tables = set(ALLOWED_TABLES + PROTECTED_TABLES)
    unknown_tables = [t for t in all_tables if t not in known_tables]
    if unknown_tables:
        print(f"\n⚠️  警告: 发现 {len(unknown_tables)} 张未知表（将跳过）:")
        for t in unknown_tables:
            print(f"    - {t}")

    # 3. 显示清空前数据量
    print(f"\n【清空前数据量】")
    pre_counts = {}
    for table in ALLOWED_TABLES:
        if table in all_tables:
            count = get_table_count(table)
            pre_counts[table] = count
            print(f"  {table}: {count} 条")

    total_pre = sum(pre_counts.values())
    print(f"\n  总计: {total_pre} 条数据")

    if total_pre == 0:
        print("\n✓ 数据库已经是空的，无需清空。")
        return 0

    # 4. 二次确认
    force = len(sys.argv) > 1 and sys.argv[1] == "--force"
    print(f"\n{'!'*70}")
    print("  ⚠️  警告: 此操作将永久删除上述所有业务数据！")
    print(f"{'!'*70}")
    if force:
        print("  [--force 模式] 跳过交互确认")
    else:
        confirm = input("\n请输入 'CLEAR' 确认清空，或输入其他内容取消: ")
        if confirm.strip() != "CLEAR":
            print("\n✗ 操作已取消。")
            return 1

    # 5. 创建备份（强制成功，失败则终止）
    print("\n【步骤 1/3】创建数据库备份...")
    try:
        backup_file = create_backup()
        print(f"  ✓ 备份已创建: {backup_file}")
    except Exception as e:
        print(f"  ✗ 备份失败: {e}")
        print("  备份失败，操作已终止（安全策略：必须先备份才能清空）。")
        return 1

    # 6. 执行清空（失败即停）
    print("\n【步骤 2/3】清空数据表...")
    cleared_counts = {}

    for table in ALLOWED_TABLES:
        if table not in all_tables:
            print(f"  ⚠️  表 {table} 不存在，跳过")
            continue

        try:
            deleted = clear_table(table)
            cleared_counts[table] = deleted
            print(f"  ✓ {table}: 已清空 {deleted} 条")
        except Exception as e:
            print(f"  ✗ {table}: 清空失败 - {e}")
            print(f"\n  错误：表 '{table}' 清空失败，操作已终止。")
            print(f"  已清空的表: {list(cleared_counts.keys())}")
            print(f"  未清空的表: {[t for t in ALLOWED_TABLES if t not in cleared_counts and t in all_tables]}")
            print(f"\n  恢复方案: mysql -u {db_info['user']} -p {db_info['name']} < {backup_file}")
            return 1

    # 7. 验证结果
    print("\n【步骤 3/3】验证清空结果...")
    verify_results = verify_cleared()

    all_cleared = all(c == 0 for c in verify_results.values())
    if all_cleared:
        print("  ✓ 所有表已清空")
    else:
        print("  ✗ 部分表未完全清空")

    # 8. 输出汇总
    print_summary(verify_results, "清空后验证结果")

    if backup_file:
        print(f"\n【备份文件】")
        print(f"  {backup_file}")
        print(f"  恢复命令: mysql -u {db_info['user']} -p {db_info['name']} < {backup_file}")

    print("\n" + "=" * 70)
    if all_cleared:
        print("  ✓ 数据库清空完成")
    else:
        print("  ⚠️ 数据库清空部分完成，请检查失败项")
    print("=" * 70)

    return 0 if all_cleared else 1


if __name__ == "__main__":
    sys.exit(main())
