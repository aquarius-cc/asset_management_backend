"""
自定义异常类

提供项目统一的异常处理:
- AppValidationError: 数据验证失败(避免与 DRF ValidationError 冲突)
- NotFoundError: 资源不存在
- PermissionDeniedError: 权限不足
- BusinessLogicError: 业务逻辑错误
- ResourceConflictError: 资源冲突
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class AppValidationError(APIException):
    """
    验证错误

    用于数据验证失败的场景,如参数格式错误、必填字段缺失等。
    支持通过 error_code 参数携带业务错误码,供批量操作使用。

    【修复 S10】重命名为 AppValidationError,避免与 DRF 的 ValidationError 冲突。

    Example:
        raise AppValidationError('参数格式错误')
        raise AppValidationError(detail={'field': '错误信息'})
        raise AppValidationError(detail='资产名称已存在', error_code='DUPLICATE_ASSET_NAME')
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "数据验证失败"
    default_code = "validation_error"

    def __init__(self, detail=None, code=None, error_code=None):
        super().__init__(detail, code)
        self.error_code = error_code


class NotFoundError(APIException):
    """
    资源不存在错误

    用于请求的资源在数据库中不存在的场景。

    Example:
        raise NotFoundError('用户不存在')
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "请求的资源不存在"
    default_code = "not_found"


class PermissionDeniedError(APIException):
    """
    权限拒绝错误

    用于用户没有权限执行某个操作的场景。

    Example:
        raise PermissionDeniedError('您没有权限删除此资源')
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "您没有权限执行此操作"
    default_code = "permission_denied"


class BusinessLogicError(APIException):
    """
    业务逻辑错误

    用于业务规则校验失败的场景,如库存不足、状态不允许等。
    支持通过 error_code 参数携带业务错误码,供批量操作使用。

    Example:
        raise BusinessLogicError('库存不足,无法出库')
        raise BusinessLogicError(detail='不能将部门移动到自己下面', error_code='CIRCULAR_REFERENCE')
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "业务逻辑错误"
    default_code = "business_logic_error"

    def __init__(self, detail=None, code=None, error_code=None):
        super().__init__(detail, code)
        self.error_code = error_code


class ResourceConflictError(APIException):
    """
    资源冲突错误

    用于资源状态冲突的场景,如重复提交、并发修改等。

    Example:
        raise ResourceConflictError('该资源已被其他用户修改')
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "资源冲突"
    default_code = "resource_conflict"


# 【P2-29 修复】保留旧名称作为别名,保持向后兼容
# 但在新代码中应使用 AppValidationError
# 注意:此别名与 rest_framework.exceptions.ValidationError 不同
# AppValidationError: 自定义异常,error_code 属性用于错误码映射
# DRF ValidationError: 框架异常,status_code=400,用于序列化器校验
ValidationError = AppValidationError
