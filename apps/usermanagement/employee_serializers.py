"""
用户管理序列化器 - 员工相关
"""

from typing import Any

from rest_framework import serializers

from apps.usermanagement.models import Department, Employee
from core.constants import MAX_BATCH_SIZE as DEFAULT_MAX_BATCH_SIZE


class EmployeeSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    员工序列化器(列表/查询用)

    【字段说明】
    - employee_department_code: 部门编码(department_code)
    - employee_department_name: 部门名称(department_name)
    - employee_department_level: 部门层级(department.level),前端用于判断部门层级
    """

    employee_department_code = serializers.SlugRelatedField(  # type: ignore[var-annotated]
        source="employee_department", slug_field="department_code", read_only=True
    )
    employee_department_name = serializers.SlugRelatedField(  # type: ignore[var-annotated]
        source="employee_department", slug_field="department_name", read_only=True
    )
    employee_department_level = serializers.IntegerField(source="employee_department.level", read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id",
            "recordcode",
            "employee_jobcode",
            "employee_name",
            "employee_status",
            "employee_department_code",
            "employee_department_name",
            "employee_department_level",
            "employee_phone",
            "employee_location",
            "employee_description",
            "sort_order",
            "is_deleted",
        ]
        read_only_fields = fields


class EmployeeDetailSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    员工详细信息序列化器(详情页用)

    【字段说明】
    - employee_department_code: 部门编码(department_code)
    - employee_department_name: 部门名称(department_name)
    - employee_department_level: 部门层级(department.level),前端用于判断部门层级
    """

    employee_department_code = serializers.SlugRelatedField(  # type: ignore[var-annotated]
        source="employee_department", slug_field="department_code", read_only=True
    )
    employee_department_name = serializers.SlugRelatedField(  # type: ignore[var-annotated]
        source="employee_department", slug_field="department_name", read_only=True
    )
    employee_department_level = serializers.IntegerField(source="employee_department.level", read_only=True)

    class Meta:
        model = Employee
        fields = "__all__"
        # 【P1-19 修复】Detail 序列化器标记关键字段为只读,防止意外写入
        read_only_fields = ["id", "recordcode", "employee_jobcode", "employee_department"]


class EmployeeCreateSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """员工创建序列化器"""

    employee_department_code = serializers.SlugRelatedField(
        source="employee_department", slug_field="department_code", queryset=Department.objects.all(), required=False
    )

    class Meta:
        model = Employee
        fields = [
            "employee_jobcode",
            "employee_name",
            "employee_status",
            "employee_department_code",
            "employee_phone",
            "employee_location",
            "employee_description",
            "sort_order",  # 【AGENTS规范】暴露排序字段
        ]

    def validate_employee_jobcode(self, value: str) -> str:
        """验证员工工号唯一性"""
        if Employee.objects.filter(employee_jobcode=value).exists():
            raise serializers.ValidationError("员工工号已存在")
        return value

    def validate_employee_phone(self, value: str) -> str:
        """验证员工电话唯一性"""
        if Employee.objects.filter(employee_phone=value).exists():
            raise serializers.ValidationError("员工电话已存在")
        return value


class EmployeeUpdateSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """员工更新序列化器"""

    employee_department_code = serializers.SlugRelatedField(
        source="employee_department", slug_field="department_code", queryset=Department.objects.all(), required=False
    )

    class Meta:
        model = Employee
        fields = [
            "employee_name",
            "employee_status",
            "employee_department_code",
            "employee_phone",
            "employee_location",
            "employee_description",
            "sort_order",  # 【AGENTS规范】暴露排序字段,支持前端调整排序
        ]


class EmployeeSortSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    员工批量排序序列化器

    用于批量更新员工的 sort_order 字段。

    【请求格式】
    {
        "items": [
            {"employee_jobcode": "E001", "sort_order": 1},
            {"employee_jobcode": "E002", "sort_order": 2},
            ...
        ]
    }
    """

    employee_jobcode = serializers.CharField(max_length=20, help_text="员工工号")
    sort_order = serializers.IntegerField(min_value=0, help_text="排序顺序,数字越小越靠前")


class EmployeeBatchSortSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """
    员工批量排序请求序列化器

    包含多个员工的排序信息。
    """

    items = EmployeeSortSerializer(many=True, help_text="员工排序项列表")


class EmployeeBatchItemSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """单条员工批量创建数据校验"""

    row_number = serializers.IntegerField(required=False, help_text="Excel 行号")
    employee_jobcode = serializers.CharField(required=True)
    employee_name = serializers.CharField(required=True)
    employee_status = serializers.CharField(required=False, default="active")
    employee_department_code = serializers.SlugRelatedField(
        source="employee_department", slug_field="department_code", queryset=Department.objects.all(), required=False
    )
    employee_phone = serializers.CharField(required=False, allow_blank=True)
    employee_location = serializers.CharField(required=False, allow_blank=True)
    employee_description = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, default=0)


class EmployeeBatchCreateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """批量创建员工请求校验"""

    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    items = EmployeeBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        # 检查工号重复
        jobcodes = [item["employee_jobcode"] for item in value]
        if len(jobcodes) != len(set(jobcodes)):
            raise serializers.ValidationError("提交记录中存在重复的员工工号")
        return value


class EmployeeBatchDeleteSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """批量删除员工请求校验"""

    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="员工工号列表")

    def validate_ids(self, value: list[str]) -> list[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
