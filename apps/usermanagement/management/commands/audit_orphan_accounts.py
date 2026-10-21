"""
管理命令：audit_orphan_accounts — 孤儿账号核查（AUD-21 批次2，只读）

用法：python manage.py audit_orphan_accounts [--json] [--active-only]

孤儿定义（与 RBAC 链路同口径，DR-1）：
    AuthUser 在 Employee.objects（默认 SoftDeleteManager，已软删不计）中
    无 employee_jobcode = auth_username 匹配行 —— 与
    core.department_scope.get_employee_for_user 的隐式关联定义完全一致。

数据面：仅 SELECT（Exists 子查询），不写库、不改状态；exit code 恒 0（核查报告非门禁）。
"""

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Exists, OuterRef

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Employee


class Command(BaseCommand):
    help = "核查孤儿账号（AuthUser 无对应未删除 Employee），只读"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出")
        parser.add_argument(
            "--active-only",
            action="store_true",
            dest="active_only",
            help="仅统计 auth_is_active=True 的账号",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # annotate 内联保留 django-stubs 的注解类型（经 helper 返回类型会剥离 → filter 关键字解析失败）
        queryset = AuthUser.objects.annotate(
            has_employee=Exists(Employee.objects.filter(employee_jobcode=OuterRef("auth_username")))
        ).order_by("auth_id")
        if options["active_only"]:
            queryset = queryset.filter(auth_is_active=True)
        rows = [self._row(user) for user in queryset.filter(has_employee=False)]
        linked = queryset.count() - len(rows)
        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    {"total": queryset.count(), "linked": linked, "orphan_count": len(rows), "orphans": rows},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        for row in rows:
            self.stdout.write(
                f"orphan auth_id={row['auth_id']} username={row['auth_username']} "
                f"active={row['auth_is_active']} staff={row['auth_is_staff']} last_login={row['last_login']}"
            )
        style = self.style.SUCCESS if not rows else self.style.WARNING
        self.stdout.write(style(f"summary total={queryset.count()} linked={linked} orphan={len(rows)}"))

    @staticmethod
    def _row(user: AuthUser) -> dict[str, Any]:
        return {
            "auth_id": user.auth_id,
            "auth_username": user.auth_username,
            "auth_is_active": user.auth_is_active,
            "auth_is_staff": user.auth_is_staff,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
