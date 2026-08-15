"""
未登记资产模块共享常量

字段白名单等跨层共享定义的唯一来源(DR-1:业务规则单一实现)。
"""

# 字段白名单:允许更新的字段(Serializer 与 Service 共用,顺序即序列化输出顺序)
UNREGISTERED_UPDATE_ALLOWED_FIELDS = (
    "scenario_type",
    "discovery_date",
    "discovery_location",
    "asset_name",
    "asset_brand",
    "asset_specification",
    "unregistered_asset_type",
    "estimated_value",
    "related_asset",
    "unregistered_asset_storage",
    "handle_description",
    "attachments",
)
