"""
为 asset_admin 授予 unregistered 模块写权限

背景:0005 迁移中 write_modules 未包含 unregistered,导致资产管理员
无 unregistered:create/update/delete 权限。按 business-rules 4.5 细则,
资产管理员(asset_admin)承担"提交发现"与待审批记录自维护职责,必须补齐。

本迁移仅做前向授权,不修改 0005 历史迁移。
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

UNREGISTERED_WRITE_ACTIONS = ["create", "update", "delete"]


def grant_unregistered_write_to_asset_admin(apps, schema_editor):
    Role = apps.get_model("usermanagement", "Role")
    Permission = apps.get_model("usermanagement", "Permission")
    RolePermission = apps.get_model("usermanagement", "RolePermission")

    try:
        role = Role.objects.get(role_code="asset_admin", is_deleted=False)
    except Role.DoesNotExist:
        logger.warning("asset_admin 角色不存在,跳过授权")
        return

    granted = 0
    for action in UNREGISTERED_WRITE_ACTIONS:
        perm = Permission.objects.filter(
            permission_code=f"unregistered:{action}",
            is_deleted=False,
        ).first()
        if not perm:
            logger.warning("权限码 unregistered:%s 不存在,跳过", action)
            continue
        _, created = RolePermission.objects.get_or_create(
            role=role,
            permission=perm,
        )
        if created:
            granted += 1

    logger.info("已为 asset_admin 授予 %d 个 unregistered 写权限", granted)


def revoke_unregistered_write_from_asset_admin(apps, schema_editor):
    Role = apps.get_model("usermanagement", "Role")
    Permission = apps.get_model("usermanagement", "Permission")
    RolePermission = apps.get_model("usermanagement", "RolePermission")

    role = Role.objects.filter(role_code="asset_admin", is_deleted=False).first()
    if not role:
        return

    codes = [f"unregistered:{action}" for action in UNREGISTERED_WRITE_ACTIONS]
    perms = Permission.objects.filter(permission_code__in=codes, is_deleted=False)
    RolePermission.objects.filter(role=role, permission__in=perms).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usermanagement", "0011_remove_department_parent_code"),
    ]

    operations = [
        migrations.RunPython(
            grant_unregistered_write_to_asset_admin,
            revoke_unregistered_write_from_asset_admin,
        ),
    ]
