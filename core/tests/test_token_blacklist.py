"""
core.token_blacklist 批量黑名单收敛测试【BF-139 / M-34】

锚定 AUD-39 修复:
- 批量 upsert: 多 token 单次 bulk_create(替代逐 token get_or_create N+1)
- 未过期过滤: expires_at <= now 的过期 token 不入黑名单
- 幂等: 已黑名单 token 不重复写入
- 失败容错: 写失败返回 0 + error 级告警, 不上抛
"""

import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.authusermanagement.models import AuthUser
from core.token_blacklist import blacklist_user_tokens


def _outstanding(user: AuthUser, jti: str, *, expired: bool = False) -> OutstandingToken:
    expires = timezone.now() + (timedelta(days=-1) if expired else timedelta(days=6))
    return OutstandingToken.objects.create(user=user, jti=jti, token=f"tok-{jti}", expires_at=expires)


@pytest.mark.django_db
class TestBlacklistUserTokens:
    def test_multiple_tokens_single_bulk_create(self):
        """多 token 应一次 bulk_create 完成(单实现批量 upsert, 非 N+1)"""
        user = AuthUser.objects.create_user(auth_username="blbatch", auth_phone="13710010020")
        for i in range(5):
            _outstanding(user, f"jti-batch-{i}")

        with patch.object(BlacklistedToken.objects, "bulk_create", wraps=BlacklistedToken.objects.bulk_create) as spy:
            created = blacklist_user_tokens(OutstandingToken.objects.filter(user=user), context="测试批量")

        assert created == 5
        assert spy.call_count == 1
        assert BlacklistedToken.objects.count() == 5

    def test_expired_tokens_skipped(self):
        """过期 token 不入黑名单(expires_at 过滤, 与注释语义对齐)"""
        user = AuthUser.objects.create_user(auth_username="blexp", auth_phone="13710010021")
        _outstanding(user, "jti-expired", expired=True)
        _outstanding(user, "jti-valid")

        created = blacklist_user_tokens(OutstandingToken.objects.filter(user=user), context="测试过期")

        assert created == 1
        blacklisted_jtis = set(BlacklistedToken.objects.values_list("token__jti", flat=True))
        assert blacklisted_jtis == {"jti-valid"}

    def test_idempotent_second_call_creates_nothing(self):
        """重复调用幂等: 已黑名单 token 不重复写入"""
        user = AuthUser.objects.create_user(auth_username="blidem", auth_phone="13710010022")
        _outstanding(user, "jti-idem")

        first = blacklist_user_tokens(OutstandingToken.objects.filter(user=user), context="测试幂等-1")
        second = blacklist_user_tokens(OutstandingToken.objects.filter(user=user), context="测试幂等-2")

        assert first == 1
        assert second == 0
        assert BlacklistedToken.objects.count() == 1

    def test_no_tokens_returns_zero(self):
        """无 token 时返回 0 且不写库"""
        user = AuthUser.objects.create_user(auth_username="blnone2", auth_phone="13710010023")

        created = blacklist_user_tokens(OutstandingToken.objects.filter(user=user), context="测试空集")

        assert created == 0
        assert BlacklistedToken.objects.count() == 0

    def test_write_failure_logs_error_and_returns_zero(self, caplog):
        """写失败: 不上抛 + error 级告警(AUD-39 失败升 error)"""
        user = AuthUser.objects.create_user(auth_username="blfail", auth_phone="13710010024")
        _outstanding(user, "jti-fail")

        def _boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("blacklist down")

        with caplog.at_level(logging.ERROR):
            with patch.object(BlacklistedToken.objects, "bulk_create", side_effect=_boom):
                created = blacklist_user_tokens(OutstandingToken.objects.filter(user=user), context="测试失败")

        assert created == 0
        assert BlacklistedToken.objects.count() == 0
        assert any(record.levelno == logging.ERROR and "黑名单操作失败" in record.message for record in caplog.records)
