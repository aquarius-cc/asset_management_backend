"""
用户管理序列化器 - 部门相关
"""

from typing import Any

from rest_framework import serializers

from apps.usermanagement.models import Department
from core.batch_mixins import BaseBatchDeleteSerializer
from core.constants import MAX_BATCH_SIZE as DEFAULT_MAX_BATCH_SIZE


class DepartmentSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    部门基础序列化器

    用于部门的 CRUD 操作和基础展示。

    输出字段:
    - parent: FK ID(recordcode)
    - parent_department_code: 业务编码(方便前端显示)
    - path: 物化路径
    """

    parent_department_code = serializers.CharField(
        source="parent.department_code", read_only=True, allow_null=True, help_text="上级部门业务编码"
    )
    parent_name = serializers.CharField(
        source="parent.department_name", read_only=True, allow_null=True, help_text="上级部门名称"
    )

    class Meta:
        model = Department
        fields = [
            "recordcode",
            "department_code",
            "department_name",
            "department_information",
            "parent",
            "parent_department_code",
            "parent_name",
            "path",
            "level",
            "sort_order",
        ]


class DepartmentTreeSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    部门树形结构序列化器

    用于返回树形结构的部门数据,包含子部门和员工数量。

    【字段说明】
    - children: 子部门列表(递归嵌套)
    - employee_count: 当前部门员工数量(仅直接关联)
    """

    # 子部门列表,递归使用自身序列化器
    children = serializers.SerializerMethodField(help_text="子部门列表")
    # 员工数量统计
    employee_count = serializers.SerializerMethodField(help_text="当前部门员工数量")
    # 父部门业务编码
    parent_department_code = serializers.CharField(
        source="parent.department_code", read_only=True, allow_null=True, help_text="上级部门业务编码"
    )

    class Meta:
        model = Department
        fields = [
            "recordcode",
            "department_code",
            "department_name",
            "department_information",
            "parent",
            "parent_department_code",
            "path",
            "level",
            "sort_order",
            "children",
            "employee_count",
        ]

    def get_children(self, obj: Department) -> Any:
        """
        获取子部门列表(使用 parent FK 查询)

        Args:
            obj: 当前部门实例

        Returns:
            list: 子部门序列化数据列表
        """
        children = Department.objects.filter(parent=obj).order_by("sort_order", "department_code")
        if not children.exists():
            return []
        # 递归序列化子部门
        return DepartmentTreeSerializer(children, many=True).data

    def get_employee_count(self, obj: Department) -> int:
        """
        获取当前部门员工数量

        Args:
            obj: 当前部门实例

        Returns:
            int: 员工数量
        """
        return obj.get_employee_count()


class DepartmentMoveSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    部门移动序列化器

    用于验证部门移动请求,修改部门的父级关系。

    【M-30 A′ 验证职责收敛】存在性/循环引用/层级约束统一由
    DepartmentService.move_department 锁内兜底(全局 handler 呈现),
    本序列化器仅做字段格式校验与 "null/none/空" 字符串归一。
    """

    target_parent_department_code = serializers.CharField(
        required=True, allow_null=True, max_length=20, help_text="目标父部门业务编码,null 表示成为根部门"
    )

    def validate_target_parent_department_code(self, value: str | None) -> str | None:
        """
        归一化目标父部门业务编码("null/none/空" 视为根部门;存在性校验在 Service)

        Args:
            value: 目标父部门业务编码

        Returns:
            归一化后的值
        """
        if value is None:
            return None

        # 处理前端可能传入的 "null" 字符串
        if isinstance(value, str) and value.lower() in ("null", "none", ""):
            return None

        return value


class DepartmentSortSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    部门批量排序序列化器

    用于批量更新部门的 sort_order 字段。

    【请求格式】
    {
        "items": [
            {"department_code": "D001", "sort_order": 1},
            {"department_code": "D002", "sort_order": 2},
            ...
        ]
    }
    """

    department_code = serializers.CharField(max_length=20, help_text="部门编码")
    sort_order = serializers.IntegerField(min_value=0, help_text="排序顺序,数字越小越靠前")


class DepartmentBatchSortSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    部门批量排序请求序列化器

    包含多个部门的排序信息。
    """

    items = DepartmentSortSerializer(many=True, help_text="部门排序项列表")

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        验证排序项列表

        Args:
            value: 排序项列表

        Returns:
            验证通过的列表

        Raises:
            serializers.ValidationError: 列表为空或部门不存在
        """
        if not value:
            raise serializers.ValidationError("排序项列表不能为空")

        # 检查所有部门是否存在
        codes = [item["department_code"] for item in value]

        # 【P2-19 修复】检查是否存在重复的部门编码
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("排序项中存在重复的部门编码")

        existing_codes = set(
            Department.objects.filter(department_code__in=codes).values_list("department_code", flat=True)
        )

        invalid_codes = set(codes) - existing_codes
        if invalid_codes:
            raise serializers.ValidationError(f"以下部门不存在: {', '.join(invalid_codes)}")

        return value


class DepartmentBatchItemSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """单条部门批量创建数据校验"""

    row_number = serializers.IntegerField(required=False, help_text="Excel 行号")
    department_code = serializers.CharField(required=True)
    department_name = serializers.CharField(required=True)
    department_information = serializers.CharField(required=False, allow_blank=True)
    parent_department_code = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, help_text="上级部门业务编码"
    )
    sort_order = serializers.IntegerField(required=False, default=0)


class DepartmentBatchCreateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """批量创建部门请求校验"""

    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    items = DepartmentBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        # 检查部门编码重复
        codes = [item["department_code"] for item in value]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("提交记录中存在重复的部门编码")
        return value


class DepartmentBatchDeleteSerializer(BaseBatchDeleteSerializer):
    """批量删除部门请求校验"""

    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="部门编码列表")
