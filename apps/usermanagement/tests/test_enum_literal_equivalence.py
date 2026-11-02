"""枚举字面量等价断言（M-08 · 批次 5，机器可验零语义漂移）。

M-08 将生产代码 7 处 role/employee_status 字面量收编为 EmployeeRole/EmployeeStatus
枚举引用。本文件以历史字面量为基线断言枚举值不漂移：任何一侧改动（如键值重排、
value 改写）都会使断言变红，避免「枚举重构 + 字面量语义漂移」的双向隐患。
"""

from apps.usermanagement.models import EmployeeRole, EmployeeStatus


def test_employee_role_dept_manager_eq_historical_literal():
    assert EmployeeRole.DEPT_MANAGER == "dept_manager"


def test_employee_status_values_eq_view_whitelist_literal_order():
    """顺序即契约:department_view 400 文案按 valid_statuses 顺序拼接,顺序漂移 = 文案变化。"""
    assert list(EmployeeStatus.values) == ["active", "left", "retirement"]
