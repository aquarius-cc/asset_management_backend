"""
用户管理Admin配置
"""

from django.contrib import admin

from apps.usermanagement.models import Department, Employee


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """
    部门管理配置

    字段说明：
    - parent: FK 指向上级部门（recordcode）
    - path: 物化路径
    - level: 部门层级
    """

    list_display = [
        "department_code",
        "department_name",
        "get_parent_code",
        "level",
        "path",
        "department_information",
        "sort_order",
    ]
    list_filter = ["level"]
    search_fields = ["department_name", "department_code"]
    ordering = ["level", "sort_order", "department_code"]
    list_editable = ["sort_order"]

    def get_parent_code(self, obj):
        """显示父部门的业务编码"""
        if obj.parent:
            return obj.parent.department_code
        return "—"

    get_parent_code.short_description = "上级部门"


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    """员工管理配置"""

    list_display = ["employee_jobcode", "employee_name", "employee_status", "employee_department", "employee_phone"]
    search_fields = ["employee_name", "employee_jobcode", "employee_phone"]
    list_filter = ["employee_status", "employee_department"]
    ordering = ["employee_jobcode"]
