"""
修复 Department.parent FK 的 to_field

问题:0002 迁移中 parent FK 默认指向 id(bigint),需要指向 recordcode(varchar)。
数据库状态:parent_id 列已存在但类型错误,需要重建。

执行逻辑:
1. 删除旧的 parent_id 列
2. 重新添加 parent_id 列,指向 recordcode
3. 重新运行数据迁移
"""

import django.db.models.deletion
from typing import Any

from django.db import migrations, models


def fix_parent_fk_and_migrate_data(apps, schema_editor):
    """
    修复 parent FK 并执行数据迁移
    """
    Department = apps.get_model('usermanagement', 'Department')

    # 1. 建立 department_code → recordcode 映射
    code_to_rc = {}
    for dept in Department.objects.filter(is_deleted=False):
        code_to_rc[dept.department_code] = dept.recordcode

    # 2. 转换 parent_code → parent_id(recordcode)
    updated_count = 0
    for dept in Department.objects.filter(is_deleted=False, parent_code__isnull=False):
        parent_rc = code_to_rc.get(dept.parent_code)
        if parent_rc:
            Department.objects.filter(pk=dept.pk).update(parent_id=parent_rc)
            updated_count += 1
        else:
            print(f"  [WARN] 部门 {dept.department_code} 的父级 {dept.parent_code} 不存在,跳过")

    print(f"  [INFO] 转换 parent FK 完成:{updated_count} 条记录")

    # 3. 生成物化路径 path
    # 建立 recordcode → department 的映射(因为 parent_id 存储的是 recordcode)
    rc_map = {}
    for dept in Department.objects.filter(is_deleted=False):
        rc_map[dept.recordcode] = dept

    # 清空所有 path 以便重新生成
    Department.objects.filter(is_deleted=False).update(path='')

    def generate_path(dept: Any) -> Any:
        if dept.parent_id is None:
            return f"/{dept.department_code}"
        # parent_id 存储的是 recordcode
        parent = rc_map.get(dept.parent_id)
        if parent:
            parent_path = generate_path(parent)
            return f"{parent_path}/{dept.department_code}"
        return f"/{dept.department_code}"

    path_updated = 0
    # 按 level 排序,确保父级 path 先生成
    all_depts = list(Department.objects.filter(is_deleted=False).order_by('level', 'sort_order'))
    for dept in all_depts:
        new_path = generate_path(dept)
        Department.objects.filter(pk=dept.pk).update(path=new_path)
        path_updated += 1

    print(f"  [INFO] 生成物化路径完成:{path_updated} 条记录")


def reverse_fix(apps, schema_editor):
    """反向迁移"""
    Department = apps.get_model('usermanagement', 'Department')
    Department.objects.all().update(parent=None, path='')


class Migration(migrations.Migration):

    dependencies = [
        ('usermanagement', '0002_rename_idx_department_parent_idx_department_parent_old_and_more'),
    ]

    operations = [
        # Stripped: all ops are no-ops (0001_initial + consolidated is source of truth)
    ]
