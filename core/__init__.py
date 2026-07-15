# d:\CodeDemo\Python\asset_management_backend\core\__init__.py
"""
Core module - 公共模型、基础组件

提供项目核心的基础类和工具：
- 基础模型类：BaseModel, TimestampModel（通过 core.models 导入）
- 自定义异常类：ValidationError, NotFoundError, PermissionDeniedError, BusinessLogicError, ResourceConflictError
- 权限类：IsOwnerOrReadOnly, IsAdminUser, IsAuthenticatedUser
- RBAC 权限类：IsSystemAdmin, IsDeptManagerOrAbove, IsAssetAdminOrAbove, IsAuditorOrAdmin

注意：模型类（BaseModel, TimestampModel）需要从 core.models 导入，
以避免 Django 应用加载顺序问题。
"""

from .exceptions import (
    APIException,
    BusinessLogicError,
    NotFoundError,
    PermissionDeniedError,
    ResourceConflictError,
    ValidationError,
)
from .permissions import (
    IsAdminUser,
    IsAssetAdminOrAbove,
    IsAuditorOrAdmin,
    IsAuthenticatedUser,
    IsDeptManagerOrAbove,
    IsOwnerOrReadOnly,
    IsSystemAdmin,
)


__all__ = [
    # 异常类
    'APIException',
    'ValidationError',
    'NotFoundError',
    'PermissionDeniedError',
    'BusinessLogicError',
    'ResourceConflictError',
    # 权限类
    'IsOwnerOrReadOnly',
    'IsAdminUser',
    'IsAuthenticatedUser',
    # RBAC 权限类
    'IsSystemAdmin',
    'IsDeptManagerOrAbove',
    'IsAssetAdminOrAbove',
    'IsAuditorOrAdmin',
]
