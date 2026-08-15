"""
公开扫码查看接口
无需认证,返回脱敏的资产基本信息
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.assetmanagement.models import Asset
from utils.response_utils import error_response, success_response


def _mask_phone(phone: str | None) -> str | None:
    """手机号脱敏:前3后4,中间用****替代"""
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]


@api_view(["GET"])
@permission_classes([AllowAny])
def public_scan_view(request: Request, recordcode: str) -> Response:
    """
    公开扫码查看资产信息(无需 JWT 认证)

    返回脱敏的资产基本信息:
    - 资产编码、名称、规格、品牌
    - 当前状态、购买价格(显示为****)
    - 存放仓库、资产分类、使用人
    - 保管人联系电话(脱敏:前3后4)
    """
    try:
        asset = Asset.objects.select_related(
            "asset_type_recordcode",
            "asset_storage_recordcode",
            "asset_manager_recordcode",
        ).get(recordcode=recordcode, is_deleted=False)
    except Asset.DoesNotExist:
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
        "asset_purchase_price": "****" if asset.asset_purchase_price else None,
        "asset_storage_name": (asset.asset_storage_recordcode.storage_name if asset.asset_storage_recordcode else None),
        "asset_type_name": (asset.asset_type_recordcode.type_name if asset.asset_type_recordcode else None),
        "asset_manager_name": (
            asset.asset_manager_recordcode.employee_name if asset.asset_manager_recordcode else None
        ),
        "asset_manager_phone": _mask_phone(
            getattr(asset.asset_manager_recordcode, "employee_phone", None) if asset.asset_manager_recordcode else None
        ),
    }

    return success_response(data=data)
