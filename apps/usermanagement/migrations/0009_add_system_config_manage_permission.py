"""
添加 system_config:manage 权限码

guards.ts 中路由守卫使用 system_config:manage 控制系统管理页面访问,
但此权限码在 0005 迁移中未创建,导致非超级管理员无法访问系统管理路由。
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def add_system_config_manage_permission(apps, schema_editor):
    Permission = apps.get_model("usermanagement", "Permission")
    RolePermission = apps.get_model("usermanagement", "RolePermission")
    Role = apps.get_model("usermanagement", "Role")

    # 创建 system_config:manage 权限
    perm, created = Permission.objects.get_or_create(
        permission_code="system_config:manage",
        defaults={
            "module": "system_config",
            "action": "manage",
            "description": "系统配置管理(资产类型、仓库、合同、用户、部门)",
        },
    )

    if created:
        # 分配给 system_admin 角色
        try:
            admin_role = Role.objects.get(role_code="system_admin", is_deleted=False)
            RolePermission.objects.get_or_create(
                role=admin_role,
                permission=perm,
            )
            logger.info("已创建权限 system_config:manage 并分配给 system_admin")
        except Role.DoesNotExist:
            logger.warning("已创建权限 system_config:manage,但 system_admin 角色不存在,跳过分配")
    else:
        logger.info("权限 system_config:manage 已存在,跳过")


def remove_system_config_manage_permission(apps, schema_editor):
    Permission = apps.get_model("usermanagement", "Permission")
    Permission.objects.filter(permission_code="system_config:manage").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usermanagement", "0008_add_employee_auth_user"),
    ]

    operations = [
        # Stripped: all ops are no-ops (0001_initial + consolidated is source of truth)
    ]
