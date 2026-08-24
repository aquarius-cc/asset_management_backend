"""
RBAC 权限体系初始数据

- 5 个角色 (system_admin, dept_manager, asset_admin, auditor, regular_user)
- 79 个权限点 (20 个模块 x 对应操作)
- 角色-权限关联 (每个角色的默认权限集)

数据从 0005_rbac_permission_tables.py 迁移至此处, 因为 Role/Permission 表
由 0015 创建, 本迁移须在其后执行。
"""

from django.db import migrations


def create_roles(apps, schema_editor):
    """创建 5 个默认角色"""
    Role = apps.get_model("usermanagement", "Role")

    roles = [
        {"role_code": "system_admin", "role_name": "系统管理员", "role_level": 5, "description": "系统管理员,拥有全部权限", "is_system": True, "sort_order": 1},
        {"role_code": "dept_manager", "role_name": "部门经理", "role_level": 4, "description": "部门经理,拥有审批权限和部门数据管理权限", "is_system": True, "sort_order": 2},
        {"role_code": "asset_admin", "role_name": "资产管理员", "role_level": 3, "description": "资产管理员,拥有资产全生命周期管理权限", "is_system": True, "sort_order": 3},
        {"role_code": "auditor", "role_name": "审计员", "role_level": 2, "description": "审计员,拥有查看和导出权限", "is_system": True, "sort_order": 4},
        {"role_code": "regular_user", "role_name": "普通用户", "role_level": 1, "description": "普通用户,仅拥有查看权限", "is_system": True, "sort_order": 5},
    ]

    for role_data in roles:
        Role.objects.get_or_create(
            role_code=role_data["role_code"],
            defaults=role_data,
        )


def create_permissions(apps, schema_editor):
    """创建 79 个权限点"""
    Permission = apps.get_model("usermanagement", "Permission")

    modules_config = {
        "asset":         {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "资产管理"},
        "outasset":      {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "出库管理"},
        "recycle":       {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "回收管理"},
        "damaged":       {"actions": ["read", "create", "update", "delete", "approve", "export"], "desc_prefix": "待报废管理"},
        "waste":         {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "已报废管理"},
        "broken":        {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "已损坏管理"},
        "lost":          {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "已遗失管理"},
        "found":         {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "找回管理"},
        "repair":        {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "维修管理"},
        "contract":      {"actions": ["read", "create", "update", "delete", "export"], "desc_prefix": "合同管理"},
        "storage":       {"actions": ["read", "create", "update", "delete"], "desc_prefix": "仓库管理"},
        "assettype":     {"actions": ["read", "create", "update", "delete"], "desc_prefix": "资产类型管理"},
        "harddisk":      {"actions": ["read", "create", "update", "delete"], "desc_prefix": "硬盘序列号管理"},
        "employee":      {"actions": ["read", "create", "update", "delete"], "desc_prefix": "员工管理"},
        "department":    {"actions": ["read", "create", "update", "delete"], "desc_prefix": "部门管理"},
        "user":          {"actions": ["read", "create", "update", "delete"], "desc_prefix": "用户管理"},
        "unregistered":  {"actions": ["read", "create", "update", "delete", "approve"], "desc_prefix": "未登记资产管理"},
        "notification":  {"actions": ["read"], "desc_prefix": "通知管理"},
        "auditlog":      {"actions": ["read", "export"], "desc_prefix": "审计日志"},
        "dashboard":     {"actions": ["read"], "desc_prefix": "仪表盘"},
    }

    action_desc_map = {
        "read": "查看",
        "create": "创建",
        "update": "编辑",
        "delete": "删除",
        "approve": "审批",
        "export": "导出",
    }

    for module, config in modules_config.items():
        for action in config["actions"]:
            permission_code = f"{module}:{action}"
            description = f"{config['desc_prefix']}{action_desc_map.get(action, action)}"
            Permission.objects.get_or_create(
                permission_code=permission_code,
                module=module,
                action=action,
                defaults={"description": description},
            )


def create_role_permissions(apps, schema_editor):
    """创建角色-权限关联"""
    Role = apps.get_model("usermanagement", "Role")
    Permission = apps.get_model("usermanagement", "Permission")
    RolePermission = apps.get_model("usermanagement", "RolePermission")

    role_map = {r.role_code: r for r in Role.objects.filter(is_deleted=False)}
    perm_map = {p.permission_code: p for p in Permission.objects.filter(is_deleted=False)}

    all_modules = [
        "asset", "outasset", "recycle", "damaged", "waste", "broken", "lost", "found", "repair",
        "contract", "storage", "assettype", "harddisk", "employee", "department", "user",
        "unregistered", "notification", "auditlog", "dashboard",
    ]
    export_modules = [
        "asset", "outasset", "recycle", "damaged", "waste", "broken", "lost", "found", "repair", "contract",
    ]
    write_modules = [
        "asset", "outasset", "recycle", "waste", "broken", "lost", "found", "repair",
    ]
    approve_modules = ["damaged", "unregistered"]

    role_permissions = {
        "system_admin": "all",
        "dept_manager": {
            "read": all_modules,
            "write": write_modules,
            "approve": approve_modules,
            "export": export_modules,
            "read_only": ["employee", "department", "user", "notification", "auditlog", "dashboard"],
        },
        "asset_admin": {
            "read": all_modules,
            "write": write_modules,
            "export": export_modules,
        },
        "auditor": {
            "read": all_modules,
            "export": export_modules,
        },
        "regular_user": {
            "read": all_modules,
        },
    }

    for role_code, perm_config in role_permissions.items():
        role = role_map.get(role_code)
        if not role:
            continue

        perms_to_add = set()

        if perm_config == "all":
            perms_to_add = set(perm_map.keys())
        else:
            if "read" in perm_config:
                for module in perm_config["read"]:
                    code = f"{module}:read"
                    if code in perm_map:
                        perms_to_add.add(code)
            if "write" in perm_config:
                for module in perm_config["write"]:
                    for action in ["create", "update", "delete"]:
                        code = f"{module}:{action}"
                        if code in perm_map:
                            perms_to_add.add(code)
            if "approve" in perm_config:
                for module in perm_config["approve"]:
                    code = f"{module}:approve"
                    if code in perm_map:
                        perms_to_add.add(code)
            if "export" in perm_config:
                for module in perm_config["export"]:
                    code = f"{module}:export"
                    if code in perm_map:
                        perms_to_add.add(code)
            if "read_only" in perm_config:
                for module in perm_config["read_only"]:
                    code = f"{module}:read"
                    if code in perm_map:
                        perms_to_add.add(code)

        for perm_code in perms_to_add:
            perm = perm_map.get(perm_code)
            if perm:
                RolePermission.objects.get_or_create(
                    role=role,
                    permission=perm,
                )


def reverse_seed(apps, schema_editor):
    RolePermission = apps.get_model("usermanagement", "RolePermission")
    Permission = apps.get_model("usermanagement", "Permission")
    Role = apps.get_model("usermanagement", "Role")

    RolePermission.objects.filter(role__is_system=True).delete()
    Permission.objects.all().delete()
    Role.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usermanagement", "0015_permission_role_rolepermission_userrole_and_more"),
    ]

    operations = [
        migrations.RunPython(create_roles, reverse_seed),
        migrations.RunPython(create_permissions, reverse_seed),
        migrations.RunPython(create_role_permissions, reverse_seed),
    ]
