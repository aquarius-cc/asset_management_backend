"""
仪表盘 ViewSet API 测试

测试 DashboardViewSet 的5个统计端点:
- trend, department_distribution, type_distribution,
  expiring_assets, maintenance_reminders
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def authenticated_client(api_client, auth_user):
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.mark.django_db
class TestDashboardTrend:
    def test_trend_returns_list(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)
        assert len(response.data["data"]) >= 30
        item = response.data["data"][0]
        assert "date" in item
        assert "new_assets" in item
        assert "distributed" in item
        assert "recovered" in item
        assert "scrapped" in item

    def test_trend_custom_days(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url, {"days": 7})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 7

    def test_trend_days_capped_at_365(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url, {"days": 999})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 300

    def test_trend_date_range(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url, {"start_date": "2026-01-01", "end_date": "2026-01-10"})
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data["data"], list)
        assert len(response.data["data"]) == 10

    def test_trend_date_range_fallback_to_days(self, authenticated_client, asset):
        """不传 start_date/end_date 时回退到 days 模式"""
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url, {"days": 5})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 5


@pytest.mark.django_db
class TestDashboardDepartmentDistribution:
    def test_returns_list(self, authenticated_client, asset, user):
        url = reverse("dashboard-department-distribution")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)

    def test_item_has_required_fields(self, authenticated_client, asset, user):
        url = reverse("dashboard-department-distribution")
        response = authenticated_client.get(url)
        if response.data["data"]:
            item = response.data["data"][0]
            assert "department_name" in item
            assert "asset_count" in item
            assert "percentage" in item


@pytest.mark.django_db
class TestDashboardTypeDistribution:
    def test_returns_list(self, authenticated_client, asset, asset_type):
        url = reverse("dashboard-type-distribution")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)

    def test_item_has_required_fields(self, authenticated_client, asset, asset_type):
        url = reverse("dashboard-type-distribution")
        response = authenticated_client.get(url)
        if response.data["data"]:
            item = response.data["data"][0]
            assert "type_name" in item
            assert "count" in item
            assert "percentage" in item


@pytest.mark.django_db
class TestDashboardExpiringAssets:
    def test_returns_list(self, authenticated_client, asset):
        url = reverse("dashboard-expiring-assets")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)

    def test_custom_days(self, authenticated_client, asset):
        url = reverse("dashboard-expiring-assets")
        response = authenticated_client.get(url, {"days": 7})
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestDashboardMaintenanceReminders:
    def test_returns_list(self, authenticated_client, asset):
        url = reverse("dashboard-maintenance-reminders")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)


def _create_scoped_auth(jobcode: str, name: str, dept, role: str, phone: str):
    """创建与 Employee 关联的认证用户(行隔离测试用)"""
    from apps.authusermanagement.models import AuthUser
    from apps.usermanagement.models import Employee
    from core.tests import TEST_PASSWORD

    AuthUser.objects.create_user(
        auth_username=jobcode, password=TEST_PASSWORD, auth_phone=phone[:-1] + "1"
    )
    Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=name,
        employee_department=dept,
        role=role,
        employee_phone=phone,
    )
    return AuthUser.objects.get(auth_username=jobcode)


@pytest.fixture
def department_b(db):
    """第二部门(用于越权隔离验证)"""
    from apps.usermanagement.models import Department

    return Department.objects.create(department_code="D002", department_name="另一部门")


@pytest.fixture
def dept_b_employee(db, department_b):
    """乙部门员工"""
    from apps.usermanagement.models import Employee

    return Employee.objects.create(
        employee_jobcode="USR_B",
        employee_name="乙部门员工",
        employee_department=department_b,
        employee_phone="13800131881",
    )


@pytest.fixture
def owned_asset(db, asset, user):
    """由甲部门员工(user/U001,部门D001)保管的资产"""
    asset.asset_manager_recordcode = user
    asset.save(update_fields=["asset_manager_recordcode"])
    return asset


@pytest.fixture
def dept_b_asset(db, storage, asset_type, dept_b_employee):
    """由乙部门员工保管的资产(应被甲部门用户隔离)"""
    from apps.assetmanagement.models import Asset

    return Asset.objects.create(
        asset_code="A002",
        asset_name="乙部门资产",
        asset_purchase_price=500.00,
        asset_purchase_date="2024-02-01",
        asset_entry_date="2024-02-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_store",
        asset_manager_recordcode=dept_b_employee,
    )


@pytest.fixture
def dept_manager_user(db, department):
    return _create_scoped_auth("DMGR", "部门经理", department, "dept_manager", "13800131901")


@pytest.fixture
def regular_a_user(db, department):
    return _create_scoped_auth("REGA", "甲部门员工", department, "regular_user", "13800131902")


@pytest.fixture
def regular_b_user(db, department_b):
    return _create_scoped_auth("REGB", "乙部门员工", department_b, "regular_user", "13800131903")


@pytest.fixture
def empty_dept_user(db):
    from apps.usermanagement.models import Department

    empty_dept = Department.objects.create(department_code="D003", department_name="空部门")
    return _create_scoped_auth("EMPTY", "空部门员工", empty_dept, "regular_user", "13800131904")


@pytest.fixture
def auditor_user(db):
    return _create_scoped_auth("AUDT", "审计专员", None, "auditor", "13800131905")


@pytest.mark.django_db
class TestDashboardRowIsolation:
    """仪表盘行级数据隔离(CT-3 补强:跨部门越权验证)"""

    def _get_overview_total(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)
        url = reverse("dashboard-overview")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        return response.data["data"]["total_assets"]

    def test_regular_user_only_sees_own_department(
        self, api_client, owned_asset, dept_b_asset, regular_a_user
    ):
        """普通用户仅见本部门资产"""
        assert self._get_overview_total(api_client, regular_a_user) == 1

    def test_regular_user_of_other_department_excluded(
        self, api_client, owned_asset, dept_b_asset, regular_b_user
    ):
        """乙部门普通用户仅见乙部门资产"""
        assert self._get_overview_total(api_client, regular_b_user) == 1

    def test_dept_manager_sees_own_department(
        self, api_client, owned_asset, dept_b_asset, dept_manager_user
    ):
        """部门经理可见本部门(含下级)资产"""
        assert self._get_overview_total(api_client, dept_manager_user) == 1

    def test_empty_department_returns_empty_data(
        self, api_client, owned_asset, dept_b_asset, empty_dept_user
    ):
        """部门级角色无本部门资产时收敛为空集"""
        assert self._get_overview_total(api_client, empty_dept_user) == 0

    def test_auditor_sees_all_departments(
        self, api_client, owned_asset, dept_b_asset, auditor_user
    ):
        """审计员为全局只读角色,可见全部资产"""
        assert self._get_overview_total(api_client, auditor_user) == 2

    def test_department_distribution_does_not_leak_other_departments(
        self, api_client, owned_asset, dept_b_asset, regular_a_user
    ):
        """部门分布不泄露其他部门名称"""
        api_client.force_authenticate(user=regular_a_user)
        url = reverse("dashboard-department-distribution")
        response = api_client.get(url)
        names = [item["department_name"] for item in response.data["data"]]
        assert names == ["测试部门"]
        assert "另一部门" not in names

    def test_recent_out_assets_scoped_to_own_department(
        self, api_client, owned_asset, dept_b_asset, regular_a_user, user, dept_b_employee
    ):
        """最近出库记录按资产部门隔离(不泄露他部门出入库人与部门名)"""
        from apps.assetmanagement.models import OutAsset

        OutAsset.objects.create(
            asset_recordcode=owned_asset,
            outasset_applicant_recordcode=user,
            outasset_date="2024-03-01",
        )
        OutAsset.objects.create(
            asset_recordcode=dept_b_asset,
            outasset_applicant_recordcode=dept_b_employee,
            outasset_date="2024-03-02",
        )
        api_client.force_authenticate(user=regular_a_user)
        url = reverse("dashboard-recent-out-assets")
        response = api_client.get(url)
        data = response.data["data"]
        assert len(data) == 1
        assert data[0]["asset_code"] == "A001"
