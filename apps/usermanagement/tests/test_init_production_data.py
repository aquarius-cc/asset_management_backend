"""
init_production_data 管理命令测试

验证:
1. 幂等性：连续执行两次，第二次零新增、无异常 (CT-4)
2. 首次部署冒烟：空库迁移后执行 → 断言角色/权限/超管数量 ≥ 最小集
3. --skip-admin 跳过超管创建
4. --dry-run 不写入数据库
5. 密码不输出到日志 (OC-3)
"""

import os
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.usermanagement.models import (
    Permission,
    Role,
    RolePermission,
)


User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestInitProductionDataIdempotency:
    """幂等性：连续执行两次，第二次零新增"""

    def test_second_run_creates_nothing(self):
        """第二次执行应创建 0 个角色/权限/关联"""
        out1 = StringIO()
        out2 = StringIO()

        with patch.dict(os.environ, {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }):
            call_command("init_production_data", stdout=out1)
            call_command("init_production_data", stdout=out2)

        output2 = out2.getvalue()
        assert "0 个新建" in output2, (
            f"第二次执行应全部为 0 新建，实际输出:\n{output2}"
        )

    def test_idempotent_with_admin(self):
        """带 admin 连续执行，超管不重复创建"""
        env = {
            "DJANGO_SUPERUSER_USERNAME": "idempotent_admin",
            "DJANGO_SUPERUSER_PASSWORD": "TestPass123!",
            "DJANGO_SUPERUSER_EMAIL": "test@test.com",
        }
        out1 = StringIO()
        out2 = StringIO()

        with patch.dict(os.environ, env, clear=False):
            call_command("init_production_data", stdout=out1)
            call_command("init_production_data", stdout=out2)

        output2 = out2.getvalue()
        assert "已存在" in output2 or "0 个新建" in output2, (
            f"第二次执行应跳过已存在的超管，实际输出:\n{output2}"
        )
        assert User.objects.filter(auth_username="idempotent_admin").count() == 1


@pytest.mark.django_db(transaction=True)
class TestInitProductionDataSmoke:
    """首次部署冒烟：断言最小数据集"""

    def test_creates_all_roles(self):
        """执行后应有 5 个默认角色"""
        out = StringIO()
        with patch.dict(os.environ, {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }):
            call_command("init_production_data", stdout=out)

        role_count = Role.objects.filter(is_deleted=False).count()
        assert role_count >= 5, f"期望至少 5 个角色，实际 {role_count}"

    def test_creates_permissions(self):
        """执行后应有 79+ 个权限点"""
        out = StringIO()
        with patch.dict(os.environ, {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }):
            call_command("init_production_data", stdout=out)

        perm_count = Permission.objects.filter(is_deleted=False).count()
        assert perm_count >= 79, f"期望至少 79 个权限点，实际 {perm_count}"

    def test_creates_role_permissions(self):
        """执行后角色-权限关联数 > 0"""
        out = StringIO()
        with patch.dict(os.environ, {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }):
            call_command("init_production_data", stdout=out)

        rp_count = RolePermission.objects.filter(is_deleted=False).count()
        assert rp_count > 0, "期望角色-权限关联数 > 0"


@pytest.mark.django_db(transaction=True)
class TestInitProductionDataSkipAdmin:
    """--skip-admin 跳过超管创建"""

    def test_skip_admin_no_user_created(self):
        """--skip-admin 不应创建超管"""
        env = {
            "DJANGO_SUPERUSER_USERNAME": "skip_admin_test",
            "DJANGO_SUPERUSER_PASSWORD": "TestPass123!",
        }
        out = StringIO()

        with patch.dict(os.environ, env, clear=False):
            call_command("init_production_data", "--skip-admin", stdout=out)

        assert not User.objects.filter(auth_username="skip_admin_test").exists()


@pytest.mark.django_db(transaction=True)
class TestInitProductionDataDryRun:
    """--dry-run 不写入数据库"""

    def test_dry_run_creates_nothing(self):
        """--dry-run 不应写入任何数据"""
        out = StringIO()
        initial_roles = Role.objects.filter(is_deleted=False).count()
        initial_perms = Permission.objects.filter(is_deleted=False).count()

        with patch.dict(os.environ, {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }):
            call_command("init_production_data", "--dry-run", stdout=out)

        assert Role.objects.filter(is_deleted=False).count() == initial_roles
        assert Permission.objects.filter(is_deleted=False).count() == initial_perms


@pytest.mark.django_db(transaction=True)
class TestInitProductionDataSecurity:
    """安全约束验证"""

    def test_password_not_in_output(self):
        """密码不得输出到日志 (OC-3)"""
        env = {
            "DJANGO_SUPERUSER_USERNAME": "sec_admin",
            "DJANGO_SUPERUSER_PASSWORD": "SuperSecret999!",
        }
        out = StringIO()

        with patch.dict(os.environ, env, clear=False):
            call_command("init_production_data", stdout=out)

        output = out.getvalue()
        assert "SuperSecret999!" not in output, (
            "密码出现在命令输出中，违反 OC-3"
        )
