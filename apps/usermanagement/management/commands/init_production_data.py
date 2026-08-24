"""
初始化生产环境基础数据（RBAC 角色/权限/管理员）

幂等设计：所有操作使用 get_or_create，可重复执行无副作用。
适用场景：
  - 全新部署：作为 entrypoint 补充保障（migration 已含初始数据）
  - 存量数据库：补齐被误删的角色/权限/关联
  - 管理员创建：通过环境变量 DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL 创建
"""

import os

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.usermanagement.models import (
    Employee,
    EmployeeRole,
    Permission,
    Role,
    RolePermission,
    UserRole,
)


User = get_user_model()

# ── 角色定义 ──────────────────────────────────────────────────────────────
ROLES = [
    {"role_code": "system_admin", "role_name": "系统管理员", "role_level": 5, "description": "系统管理员,拥有全部权限", "is_system": True, "sort_order": 1},
    {"role_code": "dept_manager", "role_name": "部门经理", "role_level": 4, "description": "部门经理,拥有审批权限和部门数据管理权限", "is_system": True, "sort_order": 2},
    {"role_code": "asset_admin", "role_name": "资产管理员", "role_level": 3, "description": "资产管理员,拥有资产全生命周期管理权限", "is_system": True, "sort_order": 3},
    {"role_code": "auditor", "role_name": "审计员", "role_level": 2, "description": "审计员,拥有查看和导出权限", "is_system": True, "sort_order": 4},
    {"role_code": "regular_user", "role_name": "普通用户", "role_level": 1, "description": "普通用户,仅拥有查看权限", "is_system": True, "sort_order": 5},
]

# ── 权限定义（module:action → description）──────────────────────────────
MODULES_CONFIG = {
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

ACTION_DESC = {
    "read": "查看", "create": "创建", "update": "编辑",
    "delete": "删除", "approve": "审批", "export": "导出",
}

# ── 角色-权限映射 ──────────────────────────────────────────────────────
ALL_MODULES = list(MODULES_CONFIG.keys())
EXPORT_MODULES = [m for m, c in MODULES_CONFIG.items() if "export" in c["actions"]]
WRITE_MODULES = [m for m, c in MODULES_CONFIG.items() if "create" in c["actions"]]
APPROVE_MODULES = [m for m, c in MODULES_CONFIG.items() if "approve" in c["actions"]]
READ_ONLY_MODULES = ["employee", "department", "user", "notification", "auditlog", "dashboard"]

ROLE_PERMISSIONS = {
    "system_admin": "all",
    "dept_manager": {
        "read": ALL_MODULES,
        "write": WRITE_MODULES,
        "approve": APPROVE_MODULES,
        "export": EXPORT_MODULES,
        "read_only": READ_ONLY_MODULES,
    },
    "asset_admin": {
        "read": ALL_MODULES,
        "write": WRITE_MODULES,
        "export": EXPORT_MODULES,
    },
    "auditor": {
        "read": ALL_MODULES,
        "export": EXPORT_MODULES,
    },
    "regular_user": {
        "read": ALL_MODULES,
    },
}


class Command(BaseCommand):
    help = "初始化生产环境基础数据（RBAC 角色/权限/关联/管理员），幂等可重复执行"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--skip-admin",
            action="store_true",
            help="跳过超级管理员创建（仅初始化 RBAC 数据）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅打印将要执行的操作，不实际写入数据库",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        skip_admin = options["skip_admin"]

        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS(" 初始化生产环境基础数据"))
        self.stdout.write(self.style.SUCCESS("=" * 50))

        # 1. 创建角色
        roles_created = self._create_roles(dry_run)

        # 2. 创建权限点
        perms_created = self._create_permissions(dry_run)

        # 3. 创建角色-权限关联
        rp_created = self._create_role_permissions(dry_run)

        # 4. 创建超级管理员
        admin_created = False
        if not skip_admin:
            admin_created = self._create_superuser(dry_run)

        # 汇总
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("-" * 50))
        self.stdout.write(self.style.SUCCESS(" 初始化完成:"))
        self.stdout.write(f"  角色: {roles_created} 个新建")
        self.stdout.write(f"  权限: {perms_created} 个新建")
        self.stdout.write(f"  角色-权限关联: {rp_created} 个新建")
        self.stdout.write(f"  超级管理员: {'已创建' if admin_created else '跳过/已存在'}")
        self.stdout.write(self.style.SUCCESS("=" * 50))

    def _create_roles(self, dry_run: bool) -> int:
        """创建 5 个默认角色"""
        self.stdout.write("\n[1/4] 检查角色...")
        count = 0
        for role_data in ROLES:
            exists = Role.objects.filter(role_code=role_data["role_code"], is_deleted=False).exists()
            if exists:
                self.stdout.write(f"  ✓ {role_data['role_code']} — 已存在")
            else:
                if dry_run:
                    self.stdout.write(f"  ○ {role_data['role_code']} — 将创建")
                else:
                    Role.objects.create(**role_data)
                    self.stdout.write(f"  + {role_data['role_code']} — 已创建")
                count += 1
        return count

    def _create_permissions(self, dry_run: bool) -> int:
        """创建 79+ 个权限点"""
        self.stdout.write("\n[2/4] 检查权限点...")
        count = 0
        for module, config in MODULES_CONFIG.items():
            for action in config["actions"]:
                code = f"{module}:{action}"
                exists = Permission.objects.filter(permission_code=code, is_deleted=False).exists()
                if exists:
                    continue
                desc = f"{config['desc_prefix']}{ACTION_DESC.get(action, action)}"
                if dry_run:
                    self.stdout.write(f"  ○ {code} — 将创建")
                else:
                    Permission.objects.create(
                        permission_code=code,
                        module=module,
                        action=action,
                        description=desc,
                    )
                count += 1
        self.stdout.write(f"  新建 {count} 个权限点")
        return count

    def _create_role_permissions(self, dry_run: bool) -> int:
        """创建角色-权限关联"""
        self.stdout.write("\n[3/4] 检查角色-权限关联...")

        role_map = {r.role_code: r for r in Role.objects.filter(is_deleted=False)}
        perm_map = {p.permission_code: p for p in Permission.objects.filter(is_deleted=False)}

        count = 0
        for role_code, perm_config in ROLE_PERMISSIONS.items():
            role = role_map.get(role_code)
            if not role:
                self.stdout.write(f"  ⚠ {role_code} — 角色不存在，跳过")
                continue

            perms_to_add: set[str] = set()

            if perm_config == "all":
                perms_to_add = set(perm_map.keys())
            else:
                for action_key, modules in perm_config.items():
                    if action_key == "read_only":
                        for mod in modules:
                            perms_to_add.add(f"{mod}:read")
                    else:
                        for mod in modules:
                            perms_to_add.add(f"{mod}:{action_key}")

            existing = set(
                RolePermission.objects.filter(role=role, is_deleted=False)
                .values_list("permission__permission_code", flat=True)
            )
            to_create = perms_to_add - existing

            for code in to_create:
                perm = perm_map.get(code)
                if not perm:
                    continue
                if dry_run:
                    self.stdout.write(f"  ○ {role_code} ← {code}")
                else:
                    RolePermission.objects.create(role=role, permission=perm)
                count += 1

            self.stdout.write(f"  {role_code}: {len(to_create)} 个新关联")
        return count

    def _create_superuser(self, dry_run: bool) -> bool:
        """通过环境变量创建超级管理员"""
        self.stdout.write("\n[4/4] 检查超级管理员...")

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")

        if not username or not password:
            self.stdout.write("  ⚠ DJANGO_SUPERUSER_USERNAME/PASSWORD 未设置，跳过")
            return False

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"  ✓ {username} — 已存在")
            return False

        if dry_run:
            self.stdout.write(f"  ○ {username} — 将创建")
            return True

        # 创建 Django 用户
        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(f"  + Django 用户 {username} — 已创建")

        # 创建或关联 Employee 记录
        employee, emp_created = Employee.objects.get_or_create(
            employee_jobcode=username,
            defaults={
                "employee_name": username,
                "role": EmployeeRole.SYSTEM_ADMIN,
                "department": "系统管理",
            },
        )
        if emp_created:
            self.stdout.write(f"  + Employee 记录 {username} — 已创建")

        # 绑定 system_admin 角色
        system_admin_role = Role.objects.filter(role_code="system_admin", is_deleted=False).first()
        if system_admin_role:
            _user_role, ur_created = UserRole.objects.get_or_create(
                user=employee,
                role=system_admin_role,
                defaults={"data_scope": {"scope_type": "all"}},
            )
            if ur_created:
                self.stdout.write(f"  + UserRole {username} ← system_admin — 已绑定")

        return True
