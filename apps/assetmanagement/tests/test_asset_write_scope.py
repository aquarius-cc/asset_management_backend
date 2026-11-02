"""资产写侧归属校验测试（BF-170 批次 3 M-01，P1 安全，[HALT] D1/D2 拍板口径落地）。

【锁定的不变量】
create / batch_create / update / change_outasset_employee 四条写路径必须经
ensure_asset_attribution_in_scope 校验（department_scope 单一事实源，DR-1）：

- 跨部门归属 → 400 ASSET_ATTRIBUTION_OUT_OF_SCOPE（D1：部门级角色只能把
  资产归属落在自身范围，dept_manager 含下级）
- 三路全空（键存在值全空）→ 400 NO_DEPARTMENT_SCOPE（D2 fail-closed；
  system_admin 同数据仍 201）
- OR 交集语义与读面 _build_department_scope_q 一致（禁 AND——存量跨部门
  资产的编辑不被误伤：多路径并集任一落在范围内即可过）
- batch_create 逐条校验：越权条目进 fail_items，不整体 400（B14 语义）
"""

from datetime import date

import pytest

from apps.assetmanagement.models import Asset
from apps.assetmanagement.services.asset_service import AssetService
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.exceptions import AppValidationError
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

_phone_seq = iter(range(20000, 30000))


def _phone() -> str:
    return f"135{next(_phone_seq):08d}"


def _make_manager(username: str, department: Department) -> AuthUser:
    """部门经理（AuthUser + Employee 同名隐式关联）。"""
    user = AuthUser.objects.create_user(auth_username=username, password=TEST_PASSWORD, auth_phone=_phone())
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}经理",
        employee_department=department,
        role=EmployeeRole.DEPT_MANAGER,
        employee_phone=_phone(),
    )
    return user


def _create_data(**overrides) -> dict:
    data = {
        "asset_name": "写面校验资产",
        "asset_purchase_price": 100,
        "asset_purchase_date": date(2024, 1, 1),
        "asset_entry_date": date(2024, 1, 15),
        "asset_purchase_number": 1,
    }
    data.update(overrides)
    return data


@pytest.fixture
def dept_a():
    return Department.objects.create(department_code="DEPT-WS-A", department_name="甲部门", path="/DEPT-WS-A")


@pytest.fixture
def dept_b():
    return Department.objects.create(department_code="DEPT-WS-B", department_name="乙部门", path="/DEPT-WS-B")


@pytest.fixture
def manager_a(dept_a):
    return _make_manager("MGR-WS-A", dept_a)


@pytest.fixture
def manager_b(dept_b):
    return _make_manager("MGR-WS-B", dept_b)


class TestCreateAttributionScope:
    def test_create_cross_department_attribution_denied(self, storage, asset_type, manager_a, manager_b):
        """甲经理创建挂乙部门入库人的资产 → 400 OUT_OF_SCOPE（D1）。"""
        employee_b = Employee.objects.get(employee_jobcode="MGR-WS-B")
        data = _create_data(asset_type_recordcode=asset_type, asset_entry_person_recordcode=employee_b)

        with pytest.raises(AppValidationError) as exc_info:
            AssetService.create_asset(data, user=manager_a)
        assert exc_info.value.error_code == "ASSET_ATTRIBUTION_OUT_OF_SCOPE"
        assert Asset.objects.filter(asset_name="写面校验资产").count() == 0

    def test_create_all_attribution_empty_dept_role_400_admin_201(self, asset_type, manager_a, full_scope_user):
        """三路全空（键存在值全空）：部门级角色 400（D2 fail-closed），system_admin 同数据 201。"""
        data = _create_data(
            asset_type_recordcode=asset_type,
            asset_manager_recordcode=None,
            asset_entry_person_recordcode=None,
            asset_storage_recordcode=None,
        )
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.create_asset(dict(data), user=manager_a)
        assert exc_info.value.error_code == "NO_DEPARTMENT_SCOPE"

        created = AssetService.create_asset(dict(data), user=full_scope_user)
        assert len(created) == 1

    def test_create_manager_to_descendant_department_201(self, storage, asset_type, manager_a, dept_a):
        """dept_manager 创建挂下级部门归属 → 201（防收紧误伤锁：descendants 展开后 OR 交集非空）。"""
        child = Department.objects.create(
            department_code="DEPT-WS-A1", department_name="甲下级", parent=dept_a, path="/DEPT-WS-A/DEPT-WS-A1", level=1
        )
        child_employee = Employee.objects.create(
            employee_jobcode="EMP-WS-A1",
            employee_name="下级员工",
            employee_department=child,
            role=EmployeeRole.REGULAR_USER,
            employee_phone=_phone(),
        )
        data = _create_data(
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_entry_person_recordcode=child_employee,
        )
        created = AssetService.create_asset(data, user=manager_a)
        assert len(created) == 1


class TestBatchCreateAttributionScope:
    def test_batch_create_mixed_partial_success(self, storage, asset_type, manager_a, manager_b):
        """混合批次：本部门条目成功、他部门条目进 fail_items（B14 逐条校验，不整体 400）。"""
        employee_a = Employee.objects.get(employee_jobcode="MGR-WS-A")
        employee_b = Employee.objects.get(employee_jobcode="MGR-WS-B")
        items = [
            _create_data(
                asset_name="批次本部门",
                asset_storage_recordcode=storage,
                asset_type_recordcode=asset_type,
                asset_entry_person_recordcode=employee_a,
            ),
            _create_data(
                asset_name="批次他部门",
                asset_storage_recordcode=storage,
                asset_type_recordcode=asset_type,
                asset_entry_person_recordcode=employee_b,
            ),
        ]
        result = AssetService.batch_create_asset(items, user=manager_a)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_ATTRIBUTION_OUT_OF_SCOPE"


class TestUpdateAttributionScope:
    def test_update_manager_to_cross_department_denied(self, storage, asset_type, manager_a, manager_b):
        """把保管人改为他部门员工（资产仅挂 manager 一条归属路径）→ 400 OUT_OF_SCOPE。"""
        employee_a = Employee.objects.get(employee_jobcode="MGR-WS-A")
        employee_b = Employee.objects.get(employee_jobcode="MGR-WS-B")
        # 资产仅 manager 一条归属(挂甲部门),由 superuser 创建后归属保持 manager 路径
        from apps.authusermanagement.models import AuthUser as _AU

        su = _AU.objects.create_superuser(auth_username="WS-SU1", password=TEST_PASSWORD, auth_phone=_phone())
        asset = AssetService.create_asset(
            _create_data(
                asset_storage_recordcode=storage,
                asset_type_recordcode=asset_type,
                asset_manager_recordcode=employee_a,
            ),
            user=su,
        )[0]

        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(asset.asset_code, {"asset_manager_recordcode": employee_b}, user=manager_a)
        assert exc_info.value.error_code == "ASSET_ATTRIBUTION_OUT_OF_SCOPE"

    def test_update_or_semantics_keeps_cross_path_editable(self, storage, asset_type, manager_a, manager_b):
        """OR 兼容锁:资产 entry 在甲(manager_a 可见),把 manager 改为乙员工 → 合并 {甲,乙} 交集非空 → 200。"""
        employee_a = Employee.objects.get(employee_jobcode="MGR-WS-A")
        employee_b = Employee.objects.get(employee_jobcode="MGR-WS-B")
        from apps.authusermanagement.models import AuthUser as _AU

        su = _AU.objects.create_superuser(auth_username="WS-SU2", password=TEST_PASSWORD, auth_phone=_phone())
        asset = AssetService.create_asset(
            _create_data(
                asset_storage_recordcode=storage,
                asset_type_recordcode=asset_type,
                asset_entry_person_recordcode=employee_a,
            ),
            user=su,
        )[0]

        updated = AssetService.update_asset(asset.asset_code, {"asset_manager_recordcode": employee_b}, user=manager_a)
        assert updated.asset_manager_recordcode.employee_department.department_code == "DEPT-WS-B"


class TestChangeOutassetEmployeeScope:
    def test_change_outasset_employee_cross_department_denied(self, storage, asset_type, manager_a, manager_b):
        """换绑保管人/使用人为乙部门双员工 → 400 OUT_OF_SCOPE（变更后归属仅乙）。

        造数口径:资产仅挂 manager 一条归属路径(甲),对 manager_a 可见;
        换绑后唯一归属路径移出甲 → 合并集 {乙} 与甲无交集 → 400。
        (若资产另有甲侧路径,OR 语义下不阻断——见 TestUpdateAttributionScope 的 OR 兼容用例)
        """
        employee_a = Employee.objects.get(employee_jobcode="MGR-WS-A")
        from apps.authusermanagement.models import AuthUser as _AU

        su = _AU.objects.create_superuser(auth_username="WS-SU3", password=TEST_PASSWORD, auth_phone=_phone())
        asset = AssetService.create_asset(
            _create_data(asset_type_recordcode=asset_type, asset_manager_recordcode=employee_a),
            user=su,
        )[0]

        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_outasset_employee(
                asset.asset_code,
                applicant_jobcode="MGR-WS-B",
                manager_jobcode="MGR-WS-B",
                user=manager_a,
            )
        assert exc_info.value.error_code == "ASSET_ATTRIBUTION_OUT_OF_SCOPE"
