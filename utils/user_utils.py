"""
用户工具函数

函数/类:
  - resolve_operator: 从用户对象解析操作人工号与姓名

调用链:
  services -> utils.user_utils -> usermanagement.models
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser


def resolve_operator(user: "AbstractBaseUser") -> tuple[str, str]:
    """解析操作人工号与姓名,按绑定机制优先级降级。

    优先级:
      1. Employee.auth_user 外键绑定(user.employee OneToOne 反向访问)
      2. 命名约定绑定(AuthUser.auth_username == Employee.employee_jobcode)
      3. 最终兜底:使用 auth_username 作为操作人标识

    依据系统同时存在的两种绑定方式(FK 与命名约定)设计,
    避免未绑定 Employee 时误用 auth_id(数字主键)污染审计字段。

    Args:
        user: 已认证的 AuthUser 实例(request.user)

    Returns:
        tuple[str, str]: (operator_jobcode, operator_name)
    """
    from apps.usermanagement.models import Employee
    from apps.usermanagement.selectors import EmployeeSelector

    try:
        employee = user.employee  # type: ignore[attr-defined]
        return employee.employee_jobcode, employee.employee_name
    except Employee.DoesNotExist:
        pass

    employee = EmployeeSelector.get_employee_by_jobcode(getattr(user, "auth_username", ""))
    if employee is not None:
        return employee.employee_jobcode, employee.employee_name

    return user.auth_username, user.auth_username  # type: ignore[attr-defined]
