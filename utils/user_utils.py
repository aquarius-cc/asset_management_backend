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
    """从当前用户的 Employee FK 反查操作人工号与姓名。

    通过 OneToOne FK 关系(Employee.auth_user)获取绑定的 Employee 记录,
    取其 employee_jobcode 和 employee_name。若用户未绑定 Employee,
    则降级使用 AuthUser 的 auth_username 作为操作人标识。

    Args:
        user: 已认证的 AuthUser 实例(request.user)

    Returns:
        tuple[str, str]: (operator_jobcode, operator_name)
    """
    from apps.usermanagement.models import Employee

    try:
        employee = user.employee
        return employee.employee_jobcode, employee.employee_name
    except Employee.DoesNotExist:
        return user.auth_username, user.auth_username
