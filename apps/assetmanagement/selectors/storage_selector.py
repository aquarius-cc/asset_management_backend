"""
仓库查询选择器

提供仓库相关的查询方法(从 base_selector.py 拆分)。
"""

from django.db.models import QuerySet

from apps.assetmanagement.models import Storage


class StorageSelector:
    """仓库查询选择器"""

    @staticmethod
    def get_all_storages() -> QuerySet[Storage]:
        return Storage.objects.filter(is_deleted=False)

    @staticmethod
    def get_storage_by_code(storage_code: str) -> Storage | None:
        try:
            return Storage.objects.get(storage_code=storage_code, is_deleted=False)
        except Storage.DoesNotExist:
            return None

    @staticmethod
    def get_storages_by_type(storage_type: str) -> QuerySet[Storage]:
        return Storage.objects.filter(storage_type=storage_type, is_deleted=False)

    @staticmethod
    def exists_by_code(storage_code: str) -> bool:
        # 【P0-21 修复】显式过滤 is_deleted=False,防御性编码
        return Storage.objects.filter(storage_code=storage_code, is_deleted=False).exists()

    @staticmethod
    def exists_by_name(storage_name: str) -> bool:
        return Storage.objects.filter(storage_name=storage_name, is_deleted=False).exists()

    @staticmethod
    def search_storages_by_keyword(keyword: str) -> QuerySet[Storage]:
        from django.db.models import Q

        return Storage.objects.filter(
            Q(storage_code__icontains=keyword)
            | Q(storage_name__icontains=keyword)
            | Q(storage_address__icontains=keyword),
            is_deleted=False,
        )
