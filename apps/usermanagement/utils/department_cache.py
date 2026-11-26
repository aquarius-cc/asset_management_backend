"""部门后代缓存失效的域内工具（Model / Service 共用）。

DR-4 定位：本模块只对 am_department 的 descendants 缓存负责，非跨业务通用工具，
故置于 apps/usermanagement/utils/ 而非仓库根 utils/。
祖先查询在函数体内延迟导入 Department，避免 models → utils → models 的模块级环。
"""

import logging
from collections.abc import Iterable

from django.core.cache import cache


# 兼容 BF-160/M-47 既有日志订阅名；warning 文案保持逐字不变。
logger = logging.getLogger("apps.usermanagement.services.department_service")


def descendants_cache_key(recordcode: str) -> str:
    """部门后代缓存键唯一构造点。"""
    return f"dept:{recordcode}:descendants"


def collect_ancestor_recordcodes(path: str) -> list[str]:
    """从物化路径收集祖先 recordcode（不含自身），缺祖先逐条 warning。"""
    from apps.usermanagement.models import Department

    if not path:
        return []
    parts = path.strip("/").split("/")
    ancestor_paths = ["/" + "/".join(parts[:i]) for i in range(1, len(parts))]
    if not ancestor_paths:
        return []
    found = dict(Department.objects.filter(path__in=ancestor_paths).values_list("path", "recordcode"))
    codes: list[str] = []
    for ancestor_path in ancestor_paths:
        recordcode = found.get(ancestor_path)
        if recordcode is not None:
            codes.append(recordcode)
        else:
            logger.warning("祖先部门不存在: path=%s ancestor_path=%s", path, ancestor_path)
    return codes


def invalidate_ancestors_cache(recordcodes: Iterable[str]) -> None:
    """批量失效祖先 descendants 缓存（delete_many 唯一实现）。"""
    keys = [descendants_cache_key(rc) for rc in recordcodes]
    if keys:
        cache.delete_many(keys)


def invalidate_self_and_ancestors_cache(recordcode: str, path: str) -> None:
    """save 后失效自身与祖先缓存（竞态窗口由下次读回填自愈）。"""
    cache.delete(descendants_cache_key(recordcode))
    invalidate_ancestors_cache(collect_ancestor_recordcodes(path))
