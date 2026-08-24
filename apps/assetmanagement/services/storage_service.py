"""
仓库管理服务

提供仓库管理的业务逻辑。
"""

import copy
from typing import Any

from django.db import transaction

from apps.assetmanagement.models import Asset, Storage
from apps.assetmanagement.selectors import StorageSelector
from core.audit_service import GenericAuditService
from core.batch_mixins import BatchOperationMixin
from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError


class StorageService:
    """
    仓库管理服务

    提供仓库管理的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_storage(
        storage_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Storage:
        """
        创建单个仓库

        Args:
            storage_data: 仓库数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            Storage: 创建成功的仓库实例

        Raises:
            AppValidationError: 仓库编码或名称已存在时抛出
        """
        storage_code = storage_data.get("storage_code")
        storage_name = storage_data.get("storage_name")

        if StorageSelector.exists_by_code(storage_code):  # type: ignore[arg-type]
            raise AppValidationError(detail=f"仓库编码 {storage_code} 已存在", error_code="DUPLICATE_STORAGE_CODE")

        if StorageSelector.exists_by_name(storage_name):  # type: ignore[arg-type]
            raise AppValidationError(detail=f"仓库名称 {storage_name} 已存在", error_code="DUPLICATE_STORAGE_NAME")

        storage = Storage.objects.create(**storage_data)

        GenericAuditService.log_create(
            record_code=storage.storage_code,
            app_label="storage",
            description=f"创建仓库: {storage.storage_name}",
            after_data={
                "storage_code": storage.storage_code,
                "storage_name": storage.storage_name,
                "storage_type": storage.storage_type,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return storage  # type: ignore[no-any-return]

    @staticmethod
    @transaction.atomic
    def delete_storage(
        storage_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """
        删除仓库(软删除)

        Args:
            storage_code: 仓库编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Raises:
            AppValidationError: 仓库不存在或存在关联资产时抛出
        """
        storage = StorageSelector.get_storage_by_code(storage_code)
        if not storage or storage.is_deleted:
            raise AppValidationError(detail=f"仓库 {storage_code} 不存在或已删除", error_code="STORAGE_NOT_FOUND")

        if Asset.objects.filter(asset_storage_recordcode=storage, is_deleted=False).exists():
            raise AppValidationError(detail="仓库下存在关联资产,不允许删除", error_code="HAS_RELATED_ASSETS")

        GenericAuditService.log_delete(
            record_code=storage.storage_code,
            app_label="storage",
            description=f"删除仓库: {storage.storage_name}",
            before_data={
                "storage_code": storage.storage_code,
                "storage_name": storage.storage_name,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        storage.delete()

    @staticmethod
    def batch_create_storage(
        storage_data_list: list[dict[str, Any]],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> dict[str, Any]:
        """
        【新增】批量创建仓库(逐条独立执行,返回详细结果)

        每条记录独立 try-except,单条失败不影响其他记录。
        复用 StorageService.create_storage() 单条创建逻辑。

        Args:
            storage_data_list: 仓库数据列表

        Returns:
            Dict[str, Any]: 批量创建结果
        """
        if len(storage_data_list) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        def _create_item(idx: int, storage_data: Any) -> Storage:
            return StorageService.create_storage(
                copy.deepcopy(storage_data),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_execute(
            items=storage_data_list,
            process_fn=_create_item,
            max_batch_size=MAX_BATCH_SIZE,
        )

    @staticmethod
    def batch_delete_storage(
        storage_codes: list[str],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> dict[str, Any]:
        """
        批量删除仓库(软删除,逐条独立执行)

        使用 BatchOperationMixin.batch_delete_execute 复用公共框架。
        """

        def _delete_item(storage_code: str) -> None:
            StorageService.delete_storage(
                storage_code,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_delete_execute(
            ids=storage_codes,
            process_fn=_delete_item,
            max_batch_size=100,
        )
