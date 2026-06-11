"""
未登记资产序列化器

该模块定义 DRF 序列化器，用于 API 请求/响应的数据验证和转换。

【AGENTS 规范 - 序列化器设计】
- 输入校验：验证字段类型、必填项、业务规则
- 输出控制：控制响应字段，保护敏感信息
- 嵌套序列化：外键字段使用 PrimaryKeyRelatedField 或 StringRelatedField
- 文档化：字段添加 help_text

【序列化器列表】
- UnregisteredAssetCreateSerializer: 创建请求
- UnregisteredAssetUpdateSerializer: 更新请求
- UnregisteredAssetApproveSerializer: 审批请求
- UnregisteredAssetListSerializer: 列表响应（精简字段）
- UnregisteredAssetDetailSerializer: 详情响应（完整字段）
"""

from rest_framework import serializers

from .models import UnregisteredAsset


class UnregisteredAssetCreateSerializer(serializers.ModelSerializer):
    """
    未登记资产创建序列化器

    用于创建未登记资产申请的请求验证。

    【校验规则】
    - scenario_type: 必填，必须是有效选项
    - asset_name: 必填，最大长度 100
    - discovery_date: 必填，日期格式
    - discovery_location: 必填，最大长度 200
    - related_asset_code: S2/S3 场景必填
    """

    class Meta:
        model = UnregisteredAsset
        fields = [
            'scenario_type',
            'discovery_date',
            'discovery_location',
            'asset_name',
            'asset_brand',
            'asset_specification',
            'asset_type_code',
            'estimated_value',
            'related_asset_code',
            'target_storage_code',
            'handle_description',
            'attachments',
        ]
        extra_kwargs = {
            'scenario_type': {
                'required': True,
                'help_text': '场景类型：s1_no_record/s2_no_outasset/s3_status_mismatch'
            },
            'discovery_date': {
                'required': True,
                'help_text': '发现日期，格式：YYYY-MM-DD'
            },
            'discovery_location': {
                'required': True,
                'help_text': '发现地点'
            },
            'asset_name': {
                'required': True,
                'help_text': '资产名称'
            },
            'asset_brand': {
                'required': False,
                'help_text': '资产品牌（可选）'
            },
            'asset_specification': {
                'required': False,
                'help_text': '资产规格（可选）'
            },
            'asset_type_code': {
                'required': False,
                'help_text': '资产类型（可选）'
            },
            'estimated_value': {
                'required': False,
                'help_text': '预估价值（可选）'
            },
            'related_asset_code': {
                'required': False,
                'help_text': '关联资产编码（S2/S3场景必填）'
            },
            'target_storage_code': {
                'required': False,
                'help_text': '目标仓库（可选）'
            },
            'handle_description': {
                'required': False,
                'help_text': '处理说明（可选）'
            },
            'attachments': {
                'required': False,
                'help_text': '附件列表（可选，JSON数组格式）'
            },
        }

    def validate(self, data: dict) -> dict:
        """
        跨字段校验

        【业务规则】
        - S2/S3 场景必须提供 related_asset_code
        - S1 场景不应提供 related_asset_code
        """
        scenario_type = data.get('scenario_type')
        related_asset_code = data.get('related_asset_code')

        if scenario_type in ['s2_no_outasset', 's3_status_mismatch']:
            if not related_asset_code:
                raise serializers.ValidationError(
                    {'related_asset_code': f'{scenario_type} 场景必须关联现有资产'}
                )

        if scenario_type == 's1_no_record' and related_asset_code:
            raise serializers.ValidationError(
                {'related_asset_code': 'S1 场景不应关联现有资产'}
            )

        return data


class UnregisteredAssetUpdateSerializer(serializers.ModelSerializer):
    """
    未登记资产更新序列化器

    用于更新未登记资产信息的请求验证。
    仅允许更新白名单内的字段。
    """

    class Meta:
        model = UnregisteredAsset
        fields = [
            'asset_name',
            'asset_brand',
            'asset_specification',
            'asset_type_code',
            'estimated_value',
            'discovery_location',
            'target_storage_code',
            'handle_description',
            'attachments',
        ]
        extra_kwargs = {
            field: {'required': False}
            for field in fields
        }


class UnregisteredAssetApproveSerializer(serializers.Serializer):
    """
    未登记资产审批序列化器

    用于审批处理的请求验证。
    """

    handle_type = serializers.ChoiceField(
        choices=[
            ('create_and_recycle', '新建资产并回收'),
            ('create_and_damaged', '新建资产并报废'),
            ('supplement_and_recycle', '补建记录并回收'),
            ('correct_and_recycle', '修正状态并回收'),
            ('reject', '拒绝处理'),
        ],
        required=True,
        help_text='处理方式'
    )
    approval_remark = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text='审批备注'
    )


class UnregisteredAssetListSerializer(serializers.ModelSerializer):
    """
    未登记资产列表序列化器

    用于列表响应，返回精简字段。
    """

    scenario_type_display = serializers.CharField(
        source='get_scenario_type_display',
        read_only=True,
        help_text='场景类型显示文本'
    )
    approval_status_display = serializers.CharField(
        source='get_approval_status_display',
        read_only=True,
        help_text='审批状态显示文本'
    )
    discovery_person_name = serializers.CharField(
        source='discovery_person_jobcode.employee_name',
        read_only=True,
        help_text='发现人姓名'
    )

    class Meta:
        model = UnregisteredAsset
        fields = [
            'id',
            'unregistered_code',
            'scenario_type',
            'scenario_type_display',
            'asset_name',
            'discovery_date',
            'discovery_location',
            'approval_status',
            'approval_status_display',
            'discovery_person_name',
            'created_at',
        ]


class UnregisteredAssetDetailSerializer(serializers.ModelSerializer):
    """
    未登记资产详情序列化器

    用于详情响应，返回完整字段。
    """

    scenario_type_display = serializers.CharField(
        source='get_scenario_type_display',
        read_only=True
    )
    handle_type_display = serializers.CharField(
        source='get_handle_type_display',
        read_only=True
    )
    approval_status_display = serializers.CharField(
        source='get_approval_status_display',
        read_only=True
    )
    discovery_person = serializers.SerializerMethodField()
    approver = serializers.SerializerMethodField()
    related_asset = serializers.SerializerMethodField()
    result_asset = serializers.SerializerMethodField()

    class Meta:
        model = UnregisteredAsset
        fields = [
            'id',
            'unregistered_code',
            'scenario_type',
            'scenario_type_display',
            'discovery_date',
            'discovery_location',
            'discovery_person',
            'asset_name',
            'asset_brand',
            'asset_specification',
            'asset_type_code',
            'estimated_value',
            'related_asset',
            'handle_type',
            'handle_type_display',
            'target_storage_code',
            'handle_description',
            'approval_status',
            'approval_status_display',
            'approver',
            'approval_date',
            'approval_remark',
            'result_asset',
            'result_recycle_code',
            'result_damaged_code',
            'attachments',
            'created_at',
            'updated_at',
        ]

    def get_discovery_person(self, obj: UnregisteredAsset) -> dict:
        """获取发现人信息"""
        if obj.discovery_person_jobcode:
            return {
                'jobcode': obj.discovery_person_jobcode.employee_jobcode,
                'name': obj.discovery_person_jobcode.employee_name,
            }
        return None

    def get_approver(self, obj: UnregisteredAsset) -> dict:
        """获取审批人信息"""
        if obj.approver_jobcode:
            return {
                'jobcode': obj.approver_jobcode.employee_jobcode,
                'name': obj.approver_jobcode.employee_name,
            }
        return None

    def get_related_asset(self, obj: UnregisteredAsset) -> dict:
        """获取关联资产信息"""
        if obj.related_asset_code:
            return {
                'code': obj.related_asset_code.asset_code,
                'name': obj.related_asset_code.asset_name,
            }
        return None

    def get_result_asset(self, obj: UnregisteredAsset) -> dict:
        """获取结果资产信息"""
        if obj.result_asset_code:
            return {
                'code': obj.result_asset_code.asset_code,
                'name': obj.result_asset_code.asset_name,
                'status': obj.result_asset_code.asset_current_status,
            }
        return None
