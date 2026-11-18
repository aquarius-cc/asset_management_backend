"""factory_boy 工厂（MA-23 包 1a）：AuthUser。

``_create`` 直接委托 ``AuthUserManager.create_user``（``authusermanagement/models.py``），
与既有 conftest 夹具同一条创建路径 —— 保证 ``set_password`` 哈希落库，
杜绝「明文密码入库」；``create_superuser`` 同理另给工厂。

默认值全静态（禁 Faker 随机）；``auth_phone`` 走 Sequence（模型有
``unique_auth_phone_active`` 条件唯一约束，空串会撞约束）。

⚠️ ``python_files = test_*.py``（pytest.ini:3），本模块不会被收集为测试文件。
"""

from __future__ import annotations

from typing import Any

import factory
from factory.django import DjangoModelFactory

from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


class AuthUserFactory(DjangoModelFactory[AuthUser]):
    """认证用户工厂（普通用户）。"""

    class Meta:
        model = AuthUser

    auth_username = factory.Sequence(lambda n: f"factoryuser{n:05d}")
    auth_phone = factory.Sequence(lambda n: f"137{n:08d}")

    @classmethod
    def _create(  # type: ignore[override]
        cls,
        model_class: type[AuthUser],
        *args: Any,
        **kwargs: Any,
    ) -> AuthUser:
        password = kwargs.pop("password", TEST_PASSWORD)
        auth_username = kwargs.pop("auth_username")
        if not auth_username:
            raise ValueError("auth_username 不能为空")
        return model_class.objects.create_user(
            auth_username=auth_username,
            password=password,
            **kwargs,
        )


class SuperUserFactory(AuthUserFactory):
    """超级管理员工厂（与 ``AuthUser.objects.create_superuser`` 同路径）。"""

    auth_is_staff = True
    is_superuser = True
