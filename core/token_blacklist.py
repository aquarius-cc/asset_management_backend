"""
Refresh Token 批量黑名单工具【BF-139 / M-34】

两处逐 token get_or_create N+1 实现收敛至此(DR-1):
- apps/authusermanagement/services.py AuthService.invalidate_user_refresh_tokens(改密吊销)
- apps/usermanagement/models.py Employee._blacklist_user_tokens(角色变更强制重登)

批量 upsert: 一次查询已黑名单集合 → 过滤差集 → bulk_create(ignore_conflicts=True),
并发下幂等不抛冲突。仅处理未过期 token(expires_at > now), 过期 token 无需黑名单。

失败取舍(注释自证): 黑名单写入失败不中断改密/改角色主流程, 旧 refresh token
最长 7 天自然过期; 但失败必须升 error 级告警日志(AUD-39)。
"""

import logging

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


logger = logging.getLogger(__name__)


def blacklist_user_tokens(outstanding: QuerySet[OutstandingToken], *, context: str) -> int:
    """批量作废给定 refresh token 集合(单实现, DR-1)

    Args:
        outstanding: 已按用户过滤的 OutstandingToken 查询集
        context: 调用方场景标识(如 "密码修改(user_id=1)"), 进入日志前缀

    Returns:
        int: 本次新增黑名单条数(写失败返回 0, 不上抛)
    """
    try:
        pending_ids = list(outstanding.filter(expires_at__gt=timezone.now()).values_list("id", flat=True))
        if not pending_ids:
            return 0

        existing = set(BlacklistedToken.objects.filter(token_id__in=pending_ids).values_list("token_id", flat=True))
        to_create = [BlacklistedToken(token_id=token_id) for token_id in pending_ids if token_id not in existing]

        if to_create:
            # 内层 atomic(savepoint): 写失败回滚至存档点, 防止外层事务被 PG 标记 abort
            with transaction.atomic():
                BlacklistedToken.objects.bulk_create(to_create, ignore_conflicts=True)
            logger.info("%s:已黑名单 %d 个 refresh token", context, len(to_create))
        return len(to_create)
    except Exception:
        logger.error(
            "%s:refresh token 黑名单操作失败, 旧 Token 仍可使用直到自然过期",
            context,
            exc_info=True,
        )
        return 0
