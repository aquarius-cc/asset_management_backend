"""全局异常处理器测试

覆盖 custom_exception_handler 对各类异常的统一响应格式。
"""

from django.http import Http404
from rest_framework import status

from core.exception_handler import custom_exception_handler
from core.exceptions import (
    AppValidationError,
    BusinessLogicError,
    NotFoundError,
    PermissionDeniedError,
    ResourceConflictError,
)


def _call_handler(exc):
    return custom_exception_handler(exc, {})


def test_app_validation_error_str_detail_returns_400():
    """AppValidationError 字符串 detail 返回 400 且 message 透传"""
    response = _call_handler(AppValidationError(detail="资产名称已存在"))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == 400
    assert response.data["message"] == "资产名称已存在"
    assert response.data["data"] == {}


def test_app_validation_error_error_code_not_exposed():
    """AppValidationError 携带 error_code 时响应体不泄露内部错误码"""
    response = _call_handler(AppValidationError(detail="用户不存在", error_code="USER_NOT_FOUND"))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error_code" not in response.data
    assert response.data["message"] == "用户不存在"


def test_app_validation_error_dict_detail_returns_generic_message_with_errors():
    """AppValidationError 字段级 detail 返回通用文案且原始错误放入 data"""
    detail = {"field_a": ["格式错误"]}
    response = _call_handler(AppValidationError(detail=detail))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "参数验证失败"
    assert response.data["data"] == detail


def test_app_validation_error_list_detail_returns_first_item():
    """AppValidationError list detail 返回首条错误信息"""
    response = _call_handler(AppValidationError(detail=["错误一", "错误二"]))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "错误一"


def test_not_found_error_returns_404():
    """NotFoundError 返回 404 且 message 透传"""
    response = _call_handler(NotFoundError("用户不存在"))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == 404
    assert response.data["message"] == "用户不存在"


def test_business_logic_error_returns_400():
    """BusinessLogicError 返回 400 且 message 透传"""
    response = _call_handler(BusinessLogicError(detail="库存不足"))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "库存不足"


def test_resource_conflict_error_returns_409():
    """ResourceConflictError 返回 409 且 message 透传"""
    response = _call_handler(ResourceConflictError("该资源已被其他用户修改"))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == 409
    assert response.data["message"] == "该资源已被其他用户修改"


def test_permission_denied_error_returns_403():
    """PermissionDeniedError 返回 403 且 message 透传"""
    response = _call_handler(PermissionDeniedError("您没有权限执行此操作"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == 403
    assert response.data["message"] == "您没有权限执行此操作"


def test_http404_returns_404():
    """Http404 被转换为 404 统一格式"""
    response = _call_handler(Http404("资源不存在"))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == 404


def test_permission_error_returns_403():
    """Python 内置 PermissionError 返回 403 不暴露内部信息"""
    response = _call_handler(PermissionError())

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == 403


def test_unknown_exception_returns_500_with_generic_message():
    """未知异常返回 500 且 message 为通用文案"""
    response = _call_handler(ValueError("boom"))

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["code"] == 500
    assert response.data["message"] == "服务器内部错误,请稍后重试"
    assert "boom" not in str(response.data["message"])


def test_drf_validation_error_field_level_returns_400():
    """DRF 序列化器字段级校验错误返回 400 且原始字段错误入 data"""
    from rest_framework.exceptions import ValidationError as DRFValidationError

    detail = {"asset_name": ["该字段是必填项。"]}
    response = _call_handler(DRFValidationError(detail=detail))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "参数验证失败"
    assert response.data["data"] == detail
