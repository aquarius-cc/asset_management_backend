


class AssetBatchItemSerializer(serializers.Serializer):
    """单条资产批量创建数据校验"""
    row_number = serializers.IntegerField(required=False, help_text="Excel 行号（前端传入，用于错误定位）")
    asset_name = serializers.CharField(required=True)
    asset_type_code = serializers.SlugRelatedField(
        queryset=AssetType.objects.filter(is_deleted=False),
        slug_field='asset_type_code',
        required=True
    )
    asset_purchase_price = serializers.DecimalField(max_digits=15, decimal_places=2, required=False)
    asset_purchase_date = serializers.DateField(required=False)
    asset_entry_date = serializers.DateField(required=False)
    asset_storage_code = serializers.SlugRelatedField(
        queryset=Storage.objects.filter(is_deleted=False),
        slug_field='storage_code',
        required=False
    )
    asset_contract_code = serializers.SlugRelatedField(
        queryset=Contract.objects.filter(is_deleted=False),
        slug_field='contract_code',
        required=False
    )
    asset_purchase_number = serializers.IntegerField(required=False, default=1, min_value=1)
    asset_department_code = serializers.SlugRelatedField(
        queryset=Department.objects.filter(is_deleted=False),
        slug_field='department_code',
        required=False
    )
    asset_employee_jobcode = serializers.SlugRelatedField(
        queryset=Employee.objects.filter(is_deleted=False),
        slug_field='employee_jobcode',
        required=False
    )
    asset_remark = serializers.CharField(required=False, allow_blank=True)


class AssetBatchCreateSerializer(serializers.Serializer):
    """批量创建请求校验"""
    MAX_BATCH_SIZE = 100
    items = AssetBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: List[Dict]) -> List[Dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条，"
                f"当前 {len(value)} 条，请分 {len(value) // self.MAX_BATCH_SIZE + 1} 批提交"
            )
        from collections import Counter
        names = [item.get('asset_name') for item in value if item.get('asset_name')]
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            raise serializers.ValidationError(
                f"提交记录中存在重复资产名称: {', '.join(duplicates)}"
            )
        return value


class AssetBatchDeleteSerializer(serializers.Serializer):
    """批量删除请求校验"""
    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        help_text="资产编码列表"
    )

    def validate_ids(self, value: List[str]) -> List[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条"
            )
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
