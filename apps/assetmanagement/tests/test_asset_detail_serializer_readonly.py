"""[OP-11] AssetDetailSerializer 兜底类全字段只读反向锁。

本类是读面专属（get_serializer_class 兜底 / mark_broken / mark_lost /
found_and_return 响应、asset_group_children_view、recycle 嵌套 read_only），
声明 read_only_fields = fields 防将来误用于写路径时 asset_current_status
等字段被直写（「未上膛的枪」上膛）。
"""

from apps.assetmanagement.serializers.asset_crud_serializers import AssetDetailSerializer


class TestAssetDetailSerializerFullyReadOnly:
    """兜底类全字段只读(OP-11 零行为约束)"""

    def test_meta_read_only_equals_fields(self):
        meta = AssetDetailSerializer.Meta
        assert meta.read_only_fields == meta.fields

    def test_all_fields_read_only_at_instantiation(self):
        serializer = AssetDetailSerializer()
        for name in AssetDetailSerializer.Meta.fields:
            assert serializer.fields[name].read_only is True, f"{name} 必须 read_only (OP-11)"

    def test_asset_current_status_read_only(self):
        serializer = AssetDetailSerializer()
        assert serializer.fields["asset_current_status"].read_only is True
