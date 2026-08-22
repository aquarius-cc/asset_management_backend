"""
公开扫码查看接口
无需认证,返回脱敏的资产基本信息
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.assetmanagement.selectors.asset_selector import AssetSelector
from utils.response_utils import error_response, success_response
from utils.string_utils import mask_phone_number


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def public_scan_view(request: Request, recordcode: str) -> Response:
    """
    公开扫码查看资产信息(无需 JWT 认证)

    返回脱敏的资产基本信息:
    - 资产编码、名称、规格、品牌
    - 当前状态、购买价格(显示为****)
    - 存放仓库、资产分类、使用人
    - 保管人联系电话(脱敏:前3后4)
    - 使用地点、入库日期、物理成色
    """
    asset = AssetSelector.get_asset_for_public_scan(recordcode)
    if asset is None:
        return error_response(
            message="未找到该资产",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 脱敏数据格式化:不在 Serializer 中处理,因为该接口为函数视图且返回脱敏数据
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
        "asset_manager_phone": mask_phone_number(
            getattr(asset.asset_manager_recordcode, "employee_phone", None)
            if asset.asset_manager_recordcode
            else None
        ),
        "asset_using_location": asset.asset_using_location,
        "asset_entry_date": asset.asset_entry_date.isoformat() if asset.asset_entry_date else None,
        "physical_grade": asset.physical_grade,
    }

    return success_response(data=data)
