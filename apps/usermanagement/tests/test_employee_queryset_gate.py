"""【MA-12】EmployeeViewSet 类属性死闸门治理回归。

约束：类属性 queryset 必须为空集闸门（防止未来旁路误用 self.queryset 绕过
get_queryset()/BF-048 行级隔离）；get_queryset() 为取行唯一入口，行为不变。
"""

from rest_framework.test import APIRequestFactory

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Employee
from apps.usermanagement.views.employee_view import EmployeeViewSet


def test_queryset_gate_and_single_entry(db, test_employee):
    """库内有行时：类属性闸门取不到行（修复前为真实全量 qs，此处先红），
    get_queryset() 仍是真实取行口径（superuser 视角 = 不限部门）。"""
    assert Employee.objects.exists()
    assert not EmployeeViewSet.queryset.exists()
    superuser = AuthUser.objects.create_user(auth_username="gate_admin", password="x" * 12, auth_phone="13800000001")
    superuser.is_superuser = True
    superuser.save(update_fields=["is_superuser"])
    request = APIRequestFactory().get("/")
    request.user = superuser
    view = EmployeeViewSet(action_map={})
    view.action = "list"
    view.request = request
    assert view.get_queryset().exists()
