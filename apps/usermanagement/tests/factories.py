"""factory_boy 工厂（MA-23 包 1a）：Department / Employee 的唯一造数实现。

设计约束（MA-23 v1.1 拍板）：
- 默认值全静态（禁 Faker 随机），保证用例确定性与可重复；
- 可空外键默认 ``None``，不用 ``SubFactory`` 兜底 —— 避免静默多造关联对象，
  进而改变既有用例的对象计数与外键断言（迁移等价性前提）；
- ``Employee.auth_user`` 恒为 ``None``：模型明文「绑定请走
  ``EmployeeService.bind_auth_user()``，禁止直接写库」
  （``apps/usermanagement/models.py`` Employee.auth_user help_text），工厂不越权；
- 存量 conftest 夹具的固定值（D001 / U001 / 13800131001 …）由夹具显式传入，
  工厂不改写、不覆盖 —— 兼容层「签名与返回值不变」由此保证。

⚠️ ``python_files = test_*.py``（pytest.ini:3），本模块不会被收集为测试文件。
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.usermanagement.models import Department, Employee


class DepartmentFactory(DjangoModelFactory[Department]):
    """部门工厂。

    默认形态与 ``apps/assetmanagement/tests/conftest.py`` 的 ``department`` 夹具同构
    （仅给 code/name，``path``/``level`` 走模型默认 ``""``/``0``）。
    需要层级部门时（``path``/``level``/``parent``）由调用方显式传入。
    """

    class Meta:
        model = Department

    department_code = factory.Sequence(lambda n: f"DFACT{n:04d}")
    department_name = factory.Sequence(lambda n: f"工厂部门{n:04d}")


class EmployeeFactory(DjangoModelFactory[Employee]):
    """员工工厂。

    ``employee_department`` 默认 ``None``（模型 ``null=True``）：不自动建部门，
    避免「建一个员工多出一个部门」的对象计数漂移。需要部门归属时显式传入。
    ``role`` / ``employee_status`` 走模型默认（regular_user / active）。
    """

    class Meta:
        model = Employee

    employee_jobcode = factory.Sequence(lambda n: f"UFACT{n:05d}")
    employee_name = factory.Sequence(lambda n: f"工厂员工{n:04d}")
    employee_phone = factory.Sequence(lambda n: f"13{n:09d}")
    employee_department = None
