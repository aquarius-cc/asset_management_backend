"""config.settings.base SC-1 守卫 + JWT 签名密钥回落测试

验证 (审查报告 #20):
1. DJANGO_SETTINGS_MODULE=config.settings.base 时模块加载即抛 ImproperlyConfigured (fail-fast)
2. 正常三层环境 (development/test_postgres) 导入不受守卫影响 (防误伤)
3. SIMPLE_JWT 不物化 SIGNING_KEY: development 下 api_settings.SIGNING_KEY 回落
   settings.SECRET_KEY (dev key), JWT 用空密钥无法解码 (锁定修复,防回归)
"""

import os
import subprocess
import sys

import pytest
from django.conf import settings

from apps.authusermanagement.models import AuthUser


def _make_user(db):
    """创建测试用 AuthUser (独立于各 app conftest, 本文件自给自足)"""
    del db  # django_db marker 已保证事务 DB 可用
    return AuthUser.objects.create_user(
        auth_username="sckey-guard-test-user",
        password="Test@12345678!",
        auth_phone="13800990011",
    )


class TestBaseSettingsGuard:
    """守卫: base.py 禁止直接部署"""

    def test_import_base_raises(self):
        """dj 误配 DJANGO_SETTINGS_MODULE=config.settings.base 时启动抛 ImproperlyConfigured"""
        env = dict(os.environ)
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.base"
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings.base"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0
        assert "ImproperlyConfigured" in result.stderr
        assert "abstract base settings" in result.stderr

    def test_development_unaffected(self):
        """development 配置导入不受守卫影响 (DJANGO_SETTINGS_MODULE=config.settings.development)"""
        import config.settings.development  # noqa: F401

        assert settings.SIMPLE_JWT.get("SIGNING_KEY") is None


class TestSigningKeyFallback:
    """JWT 签名密钥回落 settings.SECRET_KEY (不物化)"""

    def test_api_settings_signing_key_is_development_secret_key(self):
        """development 下 SIGNING_KEY == settings.SECRET_KEY (非空)"""
        from rest_framework_simplejwt.settings import api_settings

        assert api_settings.SIGNING_KEY == settings.SECRET_KEY
        assert settings.SECRET_KEY  # 非空

    @pytest.mark.django_db
    def test_empty_key_cannot_verify_token(self):
        """回归锚点: 空密钥不得再能验证 development 签发的 token"""
        import jwt
        from rest_framework_simplejwt.tokens import RefreshToken

        user = _make_user(None)
        token = str(RefreshToken.for_user(user).access_token)

        # PyJWT>=2.4 对空 HMAC key 抛 InvalidKeyError, 旧版才是 InvalidSignatureError
        with pytest.raises((jwt.InvalidSignatureError, jwt.InvalidKeyError)):
            jwt.decode(token, key="", algorithms=["HS256"])
