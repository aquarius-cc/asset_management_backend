"""contract_by_asset 豁免保护性断言（BF-170 批次 3 D4/R4 拍板）。

【拍板口径】contract_by_asset 端点数据主体为合同财务域，资产仅作查询索引条件，
不构成跨域耦合，故豁免 D4 剥离（保留 ContractDetailSerializer 含财务字段）。

豁免不等于权限盲区——本文件锁定豁免后的门禁仍在：
- 未登录 → 401（认证门禁）
- 资产行级隔离：对调用者不可见的资产 → 404（_scoped 行级过滤，不泄露存在性）
- 可见资产 → 200 且财务字段（contract_amount/amount_paid/amount_unpaid）仍在
  （付款记录页签原状，R4 拍板①）
"""

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, Contract
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

_phone_seq = iter(range(70000, 80000))


def _phone() -> str:
    return f"131{next(_phone_seq):08d}"


def _make_manager(username: str, department: Department) -> AuthUser:
    user = AuthUser.objects.create_user(auth_username=username, password=TEST_PASSWORD, auth_phone=_phone())
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}经理",
        employee_department=department,
        role=EmployeeRole.DEPT_MANAGER,
        employee_phone=_phone(),
    )
    return user


@pytest.fixture
def dept_a():
    return Department.objects.create(department_code="DEPT-CB-A", department_name="甲部门", path="/DEPT-CB-A")


@pytest.fixture
def dept_b():
    return Department.objects.create(department_code="DEPT-CB-B", department_name="乙部门", path="/DEPT-CB-B")


@pytest.fixture
def manager_a(dept_a):
    return _make_manager("MGR-CB-A", dept_a)


@pytest.fixture
def manager_b(dept_b):
    return _make_manager("MGR-CB-B", dept_b)


def _make_contract_asset(storage, asset_type, manager_user, code: str) -> Asset:
    """带合同关联、按入库人归属部门的资产（manager_user 为 AuthUser，经同名 jobcode 解析 Employee）。"""
    contract = Contract.objects.create(
        contract_code=f"CT-CB-{code}",
        contract_name=f"保护断言合同{code}",
        contract_amount=800,
        amount_paid=300,
        amount_unpaid=500,
        contract_start_date="2024-01-01",
    )
    entry_person = Employee.objects.get(employee_jobcode=manager_user.auth_username)
    return Asset.objects.create(
        recordcode=f"ASSET-CB-{code}",
        asset_code=f"CB-{code}",
        asset_name=f"保护断言资产{code}",
        asset_purchase_price=1,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_entry_person_recordcode=entry_person,
        asset_contract_recordcode=contract,
        asset_current_status="in_use",
    )


class TestContractByAssetExemptionGate:
    def test_unauthenticated_401(self, storage, asset_type, manager_a, dept_a):
        """豁免不豁免认证：未登录 → 401。"""
        _make_contract_asset(storage, asset_type, manager_a, "A1")
        client = APIClient()
        response = client.get("/api/v1/assets/assets/contract_by_asset/CB-A1/")
        assert response.status_code == 401, response.status_code

    def test_invisible_asset_404(self, storage, asset_type, manager_a, manager_b, dept_a, dept_b):
        """豁免不豁免行级隔离：乙部门经理查甲部门资产 → 404（不泄露存在性）。"""
        _make_contract_asset(storage, asset_type, manager_a, "A2")
        client = APIClient()
        client.force_authenticate(user=manager_b)
        response = client.get("/api/v1/assets/assets/contract_by_asset/CB-A2/")
        assert response.status_code == 404, response.status_code

    def test_visible_asset_returns_financial_fields(self, storage, asset_type, manager_a, dept_a):
        """可见资产 → 200 且财务三字段仍在（付款记录页签原状，R4 拍板①）。"""
        _make_contract_asset(storage, asset_type, manager_a, "A3")
        client = APIClient()
        client.force_authenticate(user=manager_a)
        response = client.get("/api/v1/assets/assets/contract_by_asset/CB-A3/")
        assert response.status_code == 200, response.status_code
        data = response.data["data"]
        # DecimalField 序列化为两位小数字符串
        assert data["contract_amount"] == "800.00"
        assert data["amount_paid"] == "300.00"
        assert data["amount_unpaid"] == "500.00"
