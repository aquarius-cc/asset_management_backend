"""
公开扫码查看接口
无需认证,仅返回 6 字段白名单内的非敏感基本信息(R4-04 最小暴露收敛)
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from utils.response_utils import error_response, success_response


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def public_scan_view(request: Request, recordcode: str) -> Response:
    """
    公开扫码查看资产信息(无需 JWT 认证)

    【R4-04 最小暴露】仅返回 6 字段白名单:
    - 资产编码、名称、规格、品牌
    - 当前状态、物理成色

    【禁暴露】价格、仓库、分类、保管人姓名/电话、使用地点、入库日期。
    成功查询记录审计日志(public_scan, 含 IP);404 不记(匿名限流兜底防刷)。
    """
    asset = AssetSelector.get_asset_for_public_scan(recordcode)
    if asset is None:
        return error_response(
            message="未找到该资产",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    data = {
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "asset_specification": asset.asset_specification,
        "asset_brand": asset.asset_brand,
        "asset_current_status": asset.asset_current_status,
        "physical_grade": asset.physical_grade,
    }

    AuditLogger.log_public_scan(
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        asset_specification=asset.asset_specification,
    )

    return success_response(data=data)
