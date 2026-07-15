"""
通用批量操作序列化器

包含 Contract、Storage、AssetType 的批量创建/删除序列化器，
这些不隶属于特定模型模块，统一归入 batch_serializers。
"""

from rest_framework import serializers


# ========== 合同批量操作序列化器 ==========


class ContractBatchDeleteSerializer(serializers.Serializer):
    """【P3-优化】批量删除合同请求校验"""

    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="合同编码列表")

    def validate_ids(self, value: list[str]) -> list[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value


class ContractBatchCreateItemSerializer(serializers.Serializer):
    """【新增】单条合同批量创建数据校验"""

    row_number = serializers.IntegerField(required=False, help_text="Excel 行号")
    contract_code = serializers.CharField(required=True, max_length=20, help_text="合同编码")
    contract_name = serializers.CharField(required=True, max_length=100, help_text="合同名称")
    contract_type = serializers.ChoiceField(
        choices=[
            ("tender_procurement", "招标采购合同"),
            ("service", "服务合同"),
            ("information_construction", "信息化建设合同"),
            ("direct_procurement", "直接采购合同"),
        ],
        required=False,
        default="tender_procurement",
        help_text="合同类型",
    )
    contract_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, help_text="合同金额", write_only=True
    )
    supplier_name = serializers.CharField(required=False, max_length=100, help_text="合同供应商")
    contract_start_date = serializers.DateField(required=False, help_text="合同开始日期")
    contract_end_date = serializers.DateField(required=False, help_text="合同结束日期")
    contract_status = serializers.ChoiceField(
        choices=[
            ("purchasing", "供货中"),
            ("purchase_finished", "供货完成"),
            ("receive_check", "到货验收"),
            ("initial_check", "初步验收"),
            ("project_settlement", "结算中"),
            ("settlement_done", "结算完成"),
            ("final_check", "最终验收"),
            ("project_finished", "项目结束"),
        ],
        required=False,
        default="purchasing",
        help_text="合同状态",
    )


class ContractBatchCreateSerializer(serializers.Serializer):
    """【新增】批量创建合同请求校验"""

    MAX_BATCH_SIZE = 100
    items = ContractBatchCreateItemSerializer(many=True, required=True)

    def validate_items(self, value: list[dict]) -> list[dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        # 检查编码重复
        codes = [item.get("contract_code") for item in value if item.get("contract_code")]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("提交记录中存在重复的合同编码")
        return value


# ========== 仓库批量操作序列化器 ==========


class StorageBatchDeleteSerializer(serializers.Serializer):
    """批量删除仓库请求校验"""

    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="仓库编码列表")

    def validate_ids(self, value: list[str]) -> list[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value


class StorageBatchCreateItemSerializer(serializers.Serializer):
    """【新增】单条仓库批量创建数据校验"""

    row_number = serializers.IntegerField(required=False, help_text="Excel 行号")
    storage_code = serializers.CharField(required=True, max_length=20, help_text="仓库编码")
    storage_name = serializers.CharField(required=True, max_length=100, help_text="仓库名称")
    storage_address = serializers.CharField(required=True, max_length=200, help_text="仓库地址")
    storage_type = serializers.ChoiceField(
        choices=[("newasset", "新货仓库"), ("recycle", "回收仓库"), ("damaged", "待报废仓库")],
        required=False,
        default="newasset",
        help_text="仓库类型",
    )
    storage_description = serializers.CharField(required=False, allow_blank=True, default="", help_text="仓库描述")


class StorageBatchCreateSerializer(serializers.Serializer):
    """【新增】批量创建仓库请求校验"""

    MAX_BATCH_SIZE = 100
    items = StorageBatchCreateItemSerializer(many=True, required=True)

    def validate_items(self, value: list[dict]) -> list[dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        # 检查编码重复
        codes = [item.get("storage_code") for item in value if item.get("storage_code")]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("提交记录中存在重复的仓库编码")
        # 检查名称重复
        names = [item.get("storage_name") for item in value if item.get("storage_name")]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("提交记录中存在重复的仓库名称")
        return value


# ========== 资产类型批量操作序列化器 ==========


class AssetTypeBatchDeleteSerializer(serializers.Serializer):
    """批量删除资产类型请求校验"""

    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="资产类型编码列表")

    def validate_ids(self, value: list[str]) -> list[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value


class AssetTypeBatchCreateItemSerializer(serializers.Serializer):
    """单条资产类型批量创建数据校验"""

    row_number = serializers.IntegerField(required=False, help_text="Excel 行号（前端传入，用于错误定位）")
    type_code = serializers.CharField(required=True, max_length=30, help_text="资产类型编码")
    type_name = serializers.CharField(required=True, max_length=100, help_text="资产类型名称")
    parent_type_code = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default="",
        help_text="父级类型业务编码"
    )
    level = serializers.IntegerField(required=False, default=0, help_text="层级")
    type_description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default="", help_text="资产类型描述"
    )
    sort_order = serializers.IntegerField(required=False, default=0, help_text="排序")


class AssetTypeBatchCreateSerializer(serializers.Serializer):
    """【新增】批量创建资产类型请求校验"""

    MAX_BATCH_SIZE = 100
    items = AssetTypeBatchCreateItemSerializer(many=True, required=True)

    def validate_items(self, value: list[dict]) -> list[dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        # 检查编码重复
        codes = [item.get("type_code") for item in value if item.get("type_code")]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("提交记录中存在重复的资产类型编码")
        return value
