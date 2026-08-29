"""
补充权限点：system_config:manage

- 来源：M-6 对抗审核发现的潜伏缺陷
- 历史：0009_add_system_config_manage_permission 的 ops 已被剥离为 no-op
        0001/0015/0016 初始化均无此码，导致该权限行从未入库
        实际使用点：前端 AsideMenu.vue:143、RolePermDialog.vue:122
- 修复策略：get_or_create 幂等，存量库新增 1 行 Permission + 1 行 RolePermission
        新库行为：与 0016 一致（system_admin 获得该权限）

本迁移仅补一条特殊权限点；模块化权限点仍由 0016 负责种子化。
"""

from django.db import migrations


SPECIAL_PERMISSIONS = [
    # (permission_code, module, action, description)
    ("system_config:manage", "system_config", "manage", "系统配置管理"),
]


def seed_special_permissions(apps, schema_editor):
    """补种特殊权限点（不在 MODULES_CONFIG 中的）"""
    Permission = apps.get_model("usermanagement", "Permission")
    for code, module, action, description in SPECIAL_PERMISSIONS:
        Permission.objects.get_or_create(
            permission_code=code,
            defaults={
                "module": module,
                "action": action,
                "description": description,
            },
        )


def seed_system_admin_link(apps, schema_editor):
    """把特殊权限关联到 system_admin（保持与 0016 system_admin="all" 等价语义）"""
    Permission = apps.get_model("usermanagement", "Permission")
    Role = apps.get_model("usermanagement", "Role")
    RolePermission = apps.get_model("usermanagement", "RolePermission")

    try:
        admin_role = Role.objects.get(role_code="system_admin", is_deleted=False)
    except Role.DoesNotExist:
        # 0016 尚未执行（极早的 fresh install 边缘场景），不阻断
        return

    for code, _, _, _ in SPECIAL_PERMISSIONS:
        try:
            perm = Permission.objects.get(permission_code=code, is_deleted=False)
        except Permission.DoesNotExist:
            continue
        RolePermission.objects.get_or_create(role=admin_role, permission=perm)


def reverse_seed_special(apps, schema_editor):
    """反向：仅删除本次新增的 1 行权限 + 1 行关联（不删其他 84 行）"""
    Permission = apps.get_model("usermanagement", "Permission")
    RolePermission = apps.get_model("usermanagement", "RolePermission")

    for code, _, _, _ in SPECIAL_PERMISSIONS:
        perms = Permission.objects.filter(permission_code=code)
        RolePermission.objects.filter(permission__in=perms).delete()
        perms.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usermanagement", "0016_seed_rbac_data"),
    ]

    operations = [
        migrations.RunPython(seed_special_permissions, reverse_seed_special),
        migrations.RunPython(seed_system_admin_link, reverse_seed_special),
    ]
