"""
角色审计适配器,封装 GenericAuditService 调用,提供统一的审计日志记录接口

类:
  - RoleAuditAdapter: 角色审计适配器(静态方法)

函数/方法:
  - log_assign_role: 记录角色分配日志
  - log_remove_role: 记录角色撤销日志
  - log_sync_permissions: 记录权限同步日志

调用链:
  本模块被 services/role_service.py 调用
  本模块依赖 core.audit_service.GenericAuditService
"""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class RoleAuditAdapter:
    """角色审计适配器"""

    @staticmethod
    def log_assign_role(
        user_id: int,
        role_id: int,
        role_name: str,
        data_scope: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """
        记录角色分配日志

        Args:
            user_id: 用户ID
            role_id: 角色ID
            role_name: 角色名称
            data_scope: 数据范围
            operator_jobcode: 操作员工号
            operator_name: 操作员姓名
        """
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_operation(
                record_code=f"user_{user_id}_role_{role_id}",
                app_label="user_role",
                operation_type="assign",
                description=f"为用户 {user_id} 分配角色: {role_name}",
                after_data={
                    "user_id": user_id,
                    "role_id": role_id,
                    "role_name": role_name,
                    "data_scope": data_scope,
                },
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录角色分配日志失败: {e}")

    @staticmethod
    def log_remove_role(
        user_id: int,
        role_id: int,
        role_name: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """
        记录角色撤销日志

        Args:
            user_id: 用户ID
            role_id: 角色ID
            role_name: 角色名称
            operator_jobcode: 操作员工号
            operator_name: 操作员姓名
        """
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_operation(
                record_code=f"user_{user_id}_role_{role_id}",
                app_label="user_role",
                operation_type="remove",
                description=f"撤销用户 {user_id} 的角色: {role_name}",
                before_data={
                    "user_id": user_id,
                    "role_id": role_id,
                    "role_name": role_name,
                },
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录角色撤销日志失败: {e}")

    @staticmethod
    def log_sync_permissions(
        role_id: int,
        role_name: str,
        perm_codes: list[str],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """
        记录权限同步日志

        Args:
            role_id: 角色ID
            role_name: 角色名称
            perm_codes: 权限码列表
            operator_jobcode: 操作员工号
            operator_name: 操作员姓名
        """
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_operation(
                record_code=f"role_{role_id}_permissions",
                app_label="role_permission",
                operation_type="sync",
                description=f"同步角色 {role_name} 的权限",
                after_data={
                    "role_id": role_id,
                    "role_name": role_name,
                    "permission_count": len(perm_codes),
                    "permission_codes": perm_codes,
                },
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录权限同步日志失败: {e}")
