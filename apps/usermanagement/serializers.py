"""
用户管理序列化器
"""
from rest_framework import serializers
from typing import Any, Dict, List, Optional
from .models import Department, Employee, MAX_DEPARTMENT_LEVEL


class DepartmentSerializer(serializers.ModelSerializer):
    """
    部门基础序列化器

    用于部门的 CRUD 操作和基础展示。
    """

    class Meta:
        model = Department
        fields = '__all__'


class DepartmentTreeSerializer(serializers.ModelSerializer):
    """
    部门树形结构序列化器

    用于返回树形结构的部门数据，包含子部门和员工数量。

    【字段说明】
    - children: 子部门列表（递归嵌套）
    - employee_count: 当前部门员工数量（仅直接关联）
    """

    # 子部门列表，递归使用自身序列化器
    children = serializers.SerializerMethodField(
        help_text="子部门列表"
    )
    # 员工数量统计
    employee_count = serializers.SerializerMethodField(
        help_text="当前部门员工数量"
    )

    class Meta:
        model = Department
        fields = [
            'department_code',
            'department_name',
            'department_information',
            'parent_code',
            'level',
            'sort_order',
            'children',
            'employee_count',
        ]

    def get_children(self, obj: Department) -> List[Dict[str, Any]]:
        """
        获取子部门列表（递归）

        Args:
            obj: 当前部门实例

        Returns:
            list: 子部门序列化数据列表
        """
        children = obj.get_children()
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


class DepartmentMoveSerializer(serializers.Serializer):
    """
    部门移动序列化器

    用于验证部门移动请求，修改部门的父级关系。

    【验证规则】
    - target_parent_code: 目标父部门编码，null 表示成为根部门
    - 移动后层级不能超过 MAX_DEPARTMENT_LEVEL
    - 不允许循环引用（不能移动到自己的子部门下）
    """

    target_parent_code = serializers.CharField(
        required=True,
        allow_null=True,
        max_length=20,
        help_text="目标父部门编码，null 表示成为根部门"
    )

    def validate_target_parent_code(self, value: Optional[str]) -> Optional[str]:
        """
        验证目标父部门编码

        Args:
            value: 目标父部门编码

        Returns:
            验证通过的值

        Raises:
            serializers.ValidationError: 父部门不存在
        """
        if value is None:
            return None

        # 检查目标父部门是否存在
        if not Department.objects.filter(department_code=value).exists():
            raise serializers.ValidationError(f"目标父部门 {value} 不存在")

        return value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        整体验证：检查循环引用和层级约束

        Args:
            attrs: 已验证的属性字典

        Returns:
            验证通过的属性字典

        Raises:
            serializers.ValidationError: 存在循环引用或层级超限
        """
        target_parent_code = attrs.get('target_parent_code')

        # 如果要成为根部门，无需额外验证
        if target_parent_code is None:
            return attrs

        # 获取当前部门（从上下文中获取）
        current_department: Optional[Department] = self.context.get('department')
        if current_department is None:
            return attrs

        # 检查是否移动到自己
        if target_parent_code == current_department.department_code:
            raise serializers.ValidationError({
                'target_parent_code': '不能将部门移动到自己下面'
            })

        # 检查循环引用：不能移动到自己的子部门下
        descendants = current_department.get_all_descendants()
        if target_parent_code in descendants:
            raise serializers.ValidationError({
                'target_parent_code': '不能将部门移动到自己的子部门下面，这会形成循环引用'
            })

        # 检查层级约束
        target_parent = Department.objects.filter(
            department_code=target_parent_code
        ).first()

        if target_parent:
            # 移动后的层级 = 目标父部门层级 + 1
            new_level = target_parent.level + 1

            # 计算当前部门的最大子树深度
            max_child_depth = self._get_max_child_depth(current_department)
            total_depth = new_level + max_child_depth

            if total_depth > MAX_DEPARTMENT_LEVEL:
                raise serializers.ValidationError({
                    'target_parent_code': f'移动后部门层级将超过 {MAX_DEPARTMENT_LEVEL} 层限制'
                })

        return attrs

    def _get_max_child_depth(self, department: Department) -> int:
        """
        计算部门的最大子树深度

        Args:
            department: 部门实例

        Returns:
            int: 最大子树深度（相对于当前部门）
        """
        children = department.get_children()
        if not children.exists():
            return 0

        max_depth = 0
        for child in children:
            child_depth = self._get_max_child_depth(child)
            max_depth = max(max_depth, child_depth + 1)

        return max_depth


class DepartmentSortSerializer(serializers.Serializer):
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

    department_code = serializers.CharField(
        max_length=20,
        help_text="部门编码"
    )
    sort_order = serializers.IntegerField(
        min_value=0,
        help_text="排序顺序，数字越小越靠前"
    )


class DepartmentBatchSortSerializer(serializers.Serializer):
    """
    部门批量排序请求序列化器

    包含多个部门的排序信息。
    """

    items = DepartmentSortSerializer(
        many=True,
        help_text="部门排序项列表"
    )

    def validate_items(self, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        codes = [item['department_code'] for item in value]
        existing_codes = set(
            Department.objects.filter(
                department_code__in=codes
            ).values_list('department_code', flat=True)
        )

        invalid_codes = set(codes) - existing_codes
        if invalid_codes:
            raise serializers.ValidationError(
                f"以下部门不存在: {', '.join(invalid_codes)}"
            )

        return value


class EmployeeSerializer(serializers.ModelSerializer):
    """员工序列化器"""
    employee_department = DepartmentSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """员工详细信息序列化器"""
    employee_department = DepartmentSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'


class EmployeeCreateSerializer(serializers.ModelSerializer):
    """员工创建序列化器"""

    class Meta:
        model = Employee
        fields = [
            'employee_jobcode', 'employee_name', 'employee_status',
            'employee_department', 'employee_phone', 'employee_location',
            'employee_description', 'sort_order'  # 【AGENTS规范】暴露排序字段
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


class EmployeeUpdateSerializer(serializers.ModelSerializer):
    """员工更新序列化器"""

    class Meta:
        model = Employee
        fields = [
            'employee_name', 'employee_status', 'employee_department',
            'employee_phone', 'employee_location', 'employee_description',
            'sort_order'  # 【AGENTS规范】暴露排序字段，支持前端调整排序
        ]

class EmployeeSortSerializer(serializers.Serializer):
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

    employee_jobcode = serializers.CharField(
        max_length=20,
        help_text="员工工号"
    )
    sort_order = serializers.IntegerField(
        min_value=0,
        help_text="排序顺序，数字越小越靠前"
    )


class EmployeeBatchSortSerializer(serializers.Serializer):
    """
    员工批量排序请求序列化器

    包含多个员工的排序信息。
    """
    items = EmployeeSortSerializer(
        many=True,
        help_text="员工排序项列表"
    )


class EmployeeBatchItemSerializer(serializers.Serializer):
    """单条员工批量创建数据校验"""
    row_number = serializers.IntegerField(required=False, help_text="Excel 行号")
    employee_jobcode = serializers.CharField(required=True)
    employee_name = serializers.CharField(required=True)
    employee_status = serializers.CharField(required=False, default='active')
    employee_department = serializers.SlugRelatedField(
        slug_field="department_code",
        queryset=Department.objects.all(),
        required=False
    )
    employee_phone = serializers.CharField(required=False, allow_blank=True)
    employee_location = serializers.CharField(required=False, allow_blank=True)
    employee_description = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, default=0)


class EmployeeBatchCreateSerializer(serializers.Serializer):
    """批量创建员工请求校验"""
    MAX_BATCH_SIZE = 100
    items = EmployeeBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: List[Dict]) -> List[Dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条"
            )
        # 检查工号重复
        jobcodes = [item['employee_jobcode'] for item in value]
        if len(jobcodes) != len(set(jobcodes)):
            raise serializers.ValidationError("提交记录中存在重复的员工工号")
        return value


class EmployeeBatchDeleteSerializer(serializers.Serializer):
    """批量删除员工请求校验"""
    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        help_text="员工工号列表"
    )

    def validate_ids(self, value: List[str]) -> List[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条"
            )
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value


class DepartmentBatchItemSerializer(serializers.Serializer):
    """单条部门批量创建数据校验"""
    row_number = serializers.IntegerField(required=False, help_text="Excel 行号")
    department_code = serializers.CharField(required=True)
    department_name = serializers.CharField(required=True)
    department_information = serializers.CharField(required=False, allow_blank=True)
    parent_code = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, default=0)


class DepartmentBatchCreateSerializer(serializers.Serializer):
    """批量创建部门请求校验"""
    MAX_BATCH_SIZE = 100
    items = DepartmentBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: List[Dict]) -> List[Dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条"
            )
        # 检查部门编码重复
        codes = [item['department_code'] for item in value]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("提交记录中存在重复的部门编码")
        return value


class DepartmentBatchDeleteSerializer(serializers.Serializer):
    """批量删除部门请求校验"""
    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        help_text="部门编码列表"
    )

    def validate_ids(self, value: List[str]) -> List[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条"
            )
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
