"""
RBAC 权限体系迁移

创建 4 个新表:
- am_role(角色表)
- am_permission(权限点表)
- am_role_permission(角色-权限中间表)
- am_user_role(用户-角色中间表)

初始数据:
- 5 个角色(system_admin, dept_manager, asset_admin, auditor, regular_user)
- 79 个权限点(20 个模块 x 对应操作)
- 角色-权限关联(每个角色的默认权限集)
"""

from django.db import migrations, models


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

    print(f"  已创建 {len(roles)} 个角色")


def create_permissions(apps, schema_editor):
    """创建 79 个权限点"""
    Permission = apps.get_model("usermanagement", "Permission")

    # 定义模块和操作
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

    count = 0
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
            count += 1

    print(f"  已创建 {count} 个权限点")


def create_role_permissions(apps, schema_editor):
    """创建角色-权限关联"""
    Role = apps.get_model("usermanagement", "Role")
    Permission = apps.get_model("usermanagement", "Permission")
    RolePermission = apps.get_model("usermanagement", "RolePermission")

    # 构建映射
    role_map = {r.role_code: r for r in Role.objects.filter(is_deleted=False)}
    perm_map = {p.permission_code: p for p in Permission.objects.filter(is_deleted=False)}

    # 定义各角色的权限集
    # 所有模块
    all_modules = [
        "asset", "outasset", "recycle", "damaged", "waste", "broken", "lost", "found", "repair",
        "contract", "storage", "assettype", "harddisk", "employee", "department", "user",
        "unregistered", "notification", "auditlog", "dashboard",
    ]

    # 导出模块(支持 export 操作的模块)
    export_modules = [
        "asset", "outasset", "recycle", "damaged", "waste", "broken", "lost", "found", "repair", "contract",
    ]

    # 写操作模块(支持 create/update/delete 的模块)
    write_modules = [
        "asset", "outasset", "recycle", "waste", "broken", "lost", "found", "repair",
    ]

    # 审批模块
    approve_modules = ["damaged", "unregistered"]

    # 定义各角色的权限
    role_permissions = {
        "system_admin": "all",  # 全部权限
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

    count = 0
    for role_code, perm_config in role_permissions.items():
        role = role_map.get(role_code)
        if not role:
            continue

        perms_to_add = set()

        if perm_config == "all":
            # system_admin: 全部权限
            perms_to_add = set(perm_map.keys())
        else:
            # 其他角色:按规则分配
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

        # 创建关联
        for perm_code in perms_to_add:
            perm = perm_map.get(perm_code)
            if perm:
                _, created = RolePermission.objects.get_or_create(
                    role=role,
                    permission=perm,
                )
                if created:
                    count += 1

    print(f"  已创建 {count} 条角色权限关联")


def reverse_create_data(apps, schema_editor):
    """反向迁移:删除初始数据"""
    RolePermission = apps.get_model("usermanagement", "RolePermission")
    Permission = apps.get_model("usermanagement", "Permission")
    Role = apps.get_model("usermanagement", "Role")

    RolePermission.objects.filter(role__is_system=True).delete()
    Permission.objects.all().delete()
    Role.objects.filter(is_system=True).delete()

    print("  已删除 RBAC 初始数据")


class Migration(migrations.Migration):

    dependencies = [
        ("usermanagement", "0004_employee_role"),
        ("authusermanagement", "0001_initial"),
    ]

    operations = [
        # 创建表
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recordcode", models.CharField(blank=True, help_text="后端生成的全局唯一编码,用于外键引用", max_length=64, null=True, unique=True, verbose_name="记录编码")),
                ("is_active", models.BooleanField(default=True, help_text="控制记录是否激活", verbose_name="是否启用")),
                ("is_deleted", models.BooleanField(default=False, help_text="软删除标记", verbose_name="是否删除")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="记录创建时间", verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="最后修改时间", verbose_name="更新时间")),
                ("role_code", models.CharField(help_text="唯一标识,如 system_admin", max_length=50, verbose_name="角色编码")),
                ("role_name", models.CharField(help_text="显示名称,如 系统管理员", max_length=100, verbose_name="角色名称")),
                ("role_level", models.IntegerField(default=0, help_text="层级值:5/4/3/2/1,用于兼容旧权限判断", verbose_name="层级值")),
                ("description", models.CharField(blank=True, max_length=500, verbose_name="角色描述")),
                ("is_system", models.BooleanField(default=False, help_text="系统内置角色不可删除", verbose_name="系统内置")),
                ("sort_order", models.IntegerField(default=0, verbose_name="排序顺序")),
            ],
            options={
                "verbose_name": "角色管理",
                "verbose_name_plural": "角色管理",
                "db_table": "am_role",
                "ordering": ["-role_level", "sort_order", "role_code"],
            },
        ),
        migrations.CreateModel(
            name="Permission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recordcode", models.CharField(blank=True, help_text="后端生成的全局唯一编码,用于外键引用", max_length=64, null=True, unique=True, verbose_name="记录编码")),
                ("is_active", models.BooleanField(default=True, help_text="控制记录是否激活", verbose_name="是否启用")),
                ("is_deleted", models.BooleanField(default=False, help_text="软删除标记", verbose_name="是否删除")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="记录创建时间", verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="最后修改时间", verbose_name="更新时间")),
                ("permission_code", models.CharField(help_text="格式:module:action,如 asset:create", max_length=100, verbose_name="权限码")),
                ("module", models.CharField(help_text="所属模块,如 asset、outasset", max_length=50, verbose_name="模块")),
                ("action", models.CharField(help_text="操作类型,如 read、create、update、delete", max_length=50, verbose_name="操作")),
                ("description", models.CharField(blank=True, max_length=200, verbose_name="权限描述")),
            ],
            options={
                "verbose_name": "权限点管理",
                "verbose_name_plural": "权限点管理",
                "db_table": "am_permission",
                "ordering": ["module", "action"],
            },
        ),
        migrations.CreateModel(
            name="RolePermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recordcode", models.CharField(blank=True, help_text="后端生成的全局唯一编码,用于外键引用", max_length=64, null=True, unique=True, verbose_name="记录编码")),
                ("is_active", models.BooleanField(default=True, help_text="控制记录是否激活", verbose_name="是否启用")),
                ("is_deleted", models.BooleanField(default=False, help_text="软删除标记", verbose_name="是否删除")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="记录创建时间", verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="最后修改时间", verbose_name="更新时间")),
                ("role", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="role_permissions", to="usermanagement.role", verbose_name="角色")),
                ("permission", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="role_permissions", to="usermanagement.permission", verbose_name="权限点")),
            ],
            options={
                "verbose_name": "角色权限关联",
                "verbose_name_plural": "角色权限关联",
                "db_table": "am_role_permission",
            },
        ),
        migrations.CreateModel(
            name="UserRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recordcode", models.CharField(blank=True, help_text="后端生成的全局唯一编码,用于外键引用", max_length=64, null=True, unique=True, verbose_name="记录编码")),
                ("is_active", models.BooleanField(default=True, help_text="控制记录是否激活", verbose_name="是否启用")),
                ("is_deleted", models.BooleanField(default=False, help_text="软删除标记", verbose_name="是否删除")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="记录创建时间", verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="最后修改时间", verbose_name="更新时间")),
                ("data_scope", models.JSONField(blank=True, default=dict, help_text='JSON 格式:{"scope_type": "all"} 或 {"scope_type": "department", "department_code": "IT-001", "include_children": true}', verbose_name="数据范围")),
                ("auth_user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="user_roles", to="authusermanagement.authuser", verbose_name="系统账号")),
                ("role", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="user_roles", to="usermanagement.role", verbose_name="角色")),
            ],
            options={
                "verbose_name": "用户角色关联",
                "verbose_name_plural": "用户角色关联",
                "db_table": "am_user_role",
            },
        ),
        # 添加约束
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(condition=models.Q(is_deleted=False), fields=("role_code",), name="unique_role_code_not_deleted"),
        ),
        migrations.AddConstraint(
            model_name="permission",
            constraint=models.UniqueConstraint(condition=models.Q(is_deleted=False), fields=("permission_code",), name="unique_permission_code_not_deleted"),
        ),
        migrations.AddConstraint(
            model_name="permission",
            constraint=models.UniqueConstraint(condition=models.Q(is_deleted=False), fields=("module", "action"), name="unique_module_action_not_deleted"),
        ),
        migrations.AddConstraint(
            model_name="rolepermission",
            constraint=models.UniqueConstraint(fields=("role", "permission"), name="unique_role_permission"),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(fields=("auth_user", "role"), name="unique_user_role"),
        ),
        # 添加索引
        migrations.AddIndex(
            model_name="userrole",
            index=models.Index(fields=["auth_user"], name="idx_ur_auth_user"),
        ),
        migrations.AddIndex(
            model_name="userrole",
            index=models.Index(fields=["role"], name="idx_ur_role"),
        ),
        # 插入初始数据
        migrations.RunPython(create_roles, reverse_create_data),
        migrations.RunPython(create_permissions, reverse_create_data),
        migrations.RunPython(create_role_permissions, reverse_create_data),
    ]
