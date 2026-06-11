"""
用户管理Admin配置
"""
from django.contrib import admin
from .models import Department, Employee


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """
    部门管理配置

    【新增字段】
    - parent_code: 上级部门编码
    - level: 部门层级
    """
    list_display = [
        'department_code',
        'department_name',
        'parent_code',
        'level',
        'department_information',
        'sort_order'
    ]
    list_filter = ['level', 'parent_code']
    search_fields = ['department_name', 'department_code']
    ordering = ['level', 'sort_order', 'department_code']
    list_editable = ['sort_order', 'parent_code']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    """员工管理配置"""
    list_display = ['employee_jobcode', 'employee_name', 'employee_status', 'employee_department', 'employee_phone']
    search_fields = ['employee_name', 'employee_jobcode', 'employee_phone']
    list_filter = ['employee_status', 'employee_department']
    ordering = ['employee_jobcode']