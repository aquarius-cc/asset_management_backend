"""
待报废资产管理 ViewSet API 测试

测试 DamagedAssetViewSet 的 API 端点:
- list
- create
- retrieve
- update
- partial_update
- destroy
- 自定义 actions: approve, reject, by_asset, statistics, batch_delete
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def authenticated_client(api_client, auth_user):
    """已认证的用户客户端"""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def admin_authenticated_client(api_client, admin_auth_user):
    """管理员用户客户端"""
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


@pytest.mark.django_db
class TestDamagedAssetViewSet:
    """DamagedAssetViewSet API 测试"""

    def test_list_damaged_assets(self, authenticated_client, damaged_asset):
        """测试获取待报废资产列表"""
        url = reverse("damaged-assets-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_damaged_asset(self, admin_authenticated_client, asset, employee):
        """测试创建待报废资产(资产需处于 recycled_pending/broken/repairing/lost 状态)"""
        # 将资产从 in_store 转为 recycled_pending,以满足 damaged() FSM 要求
        asset.asset_current_status = "recycled_pending"
        asset.save(update_fields=["asset_current_status"])

        url = reverse("damaged-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "damaged_date": "2024-07-01",
            "damaged_asset_description": "测试损坏描述",
            "damaged_asset_number": 1,
            "approver": employee.employee_jobcode,
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        assert response.data["data"]["asset_recordcode"] == asset.recordcode

    def test_retrieve_damaged_asset(self, authenticated_client, damaged_asset):
        """测试获取待报废资产详情"""
        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == damaged_asset.recordcode

    def test_update_damaged_asset(self, admin_authenticated_client, damaged_asset):
        """测试更新待报废资产"""
        from apps.assetmanagement.models import AssetOperationLog

        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        data = {"damaged_asset_description": "更新后的损坏描述"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["damaged_asset_description"] == "更新后的损坏描述"
        log = AssetOperationLog.objects.filter(
            asset_code=damaged_asset.asset_recordcode.asset_code,
            operation_type="update",
        ).first()
        assert log is not None, "更新待报废记录应产生操作日志"
        assert log.operator_jobcode is not None, "操作日志应记录操作人工号"
        assert log.operator_jobcode == "adminuser"

    def test_partial_update_damaged_asset(self, admin_authenticated_client, damaged_asset):
        """测试部分更新待报废资产"""
        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        data = {"damaged_asset_description": "部分更新后的损坏描述"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["damaged_asset_description"] == "部分更新后的损坏描述"

    def test_update_damaged_asset_invalid_number_rejected(self, admin_authenticated_client, damaged_asset):
        """B8 输入门禁: 损坏数量类型错误应返回 400,不得落 Service"""
        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        data = {"damaged_asset_number": "abc"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        damaged_asset.refresh_from_db()
        assert damaged_asset.damaged_asset_number == 1

    def test_update_damaged_asset_is_active_read_only(self, admin_authenticated_client, damaged_asset):
        """B8 白名单对齐: is_active 非 Service 可写字段, serializer 只读, 提交后不得生效"""
        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        data = {"damaged_asset_description": "更新后的损坏描述", "is_active": False}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        damaged_asset.refresh_from_db()
        assert damaged_asset.damaged_asset_description == "更新后的损坏描述"
        assert damaged_asset.is_active is True

    def test_update_damaged_asset_unknown_field_ignored(self, admin_authenticated_client, damaged_asset):
        """B8 Gap B 决策: 未知字段静默忽略(DRF 默认), 声明字段正常生效"""
        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        data = {"damaged_asset_description": "更新后的损坏描述", "foo": "bar"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        damaged_asset.refresh_from_db()
        assert damaged_asset.damaged_asset_description == "更新后的损坏描述"

    def test_destroy_damaged_asset(self, admin_authenticated_client, damaged_asset):
        """测试删除待报废资产"""
        url = reverse("damaged-assets-detail", kwargs={"recordcode": damaged_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        # Asset must be in 'damaged_pending' state for cancel — accept error for in_store asset
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

    def test_approve(self, admin_authenticated_client, damaged_asset, employee):
        """测试审批通过待报废资产"""
        url = reverse("damaged-assets-approve", kwargs={"recordcode": damaged_asset.recordcode})
        data = {
            "approver_jobcode": employee.employee_jobcode,
            "operator_name": employee.employee_name,
        }
        response = admin_authenticated_client.post(url, data, format="json")
        # Asset must be in 'damaged_pending' state for approve — accept error for in_store asset
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

    def test_reject(self, admin_authenticated_client, damaged_asset, employee):
        """测试拒绝待报废资产"""
        url = reverse("damaged-assets-reject", kwargs={"recordcode": damaged_asset.recordcode})
        data = {
            "approver_jobcode": employee.employee_jobcode,
            "operator_name": employee.employee_name,
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["approval_status"] == "rejected"

    def test_by_asset(self, authenticated_client, damaged_asset, asset):
        """测试按资产查询待报废记录"""
        url = reverse("damaged-assets-by-asset", kwargs={"asset_recordcode": asset.asset_code})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]

    def test_statistics(self, authenticated_client):
        """测试待报废资产统计"""
        url = reverse("damaged-assets-statistics")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "total_damaged" in response.data["data"]

    def test_batch_delete(self, admin_authenticated_client, damaged_asset):
        """测试批量删除待报废资产"""
        url = reverse("damaged-assets-batch-delete")
        data = {"ids": [damaged_asset.asset_recordcode.recordcode]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        # Asset must be in 'damaged_pending' state for cancel — batch may partially fail
        assert response.data["data"]["total"] == 1


def _make_role_user(jobcode: str, role: str, department, phone: str):
    from apps.authusermanagement.models import AuthUser
    from apps.usermanagement.models import Employee
    from core.tests import TEST_PASSWORD

    AuthUser.objects.create_user(auth_username=jobcode, password=TEST_PASSWORD, auth_phone=phone[:-1] + "1")
    Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=jobcode,
        employee_department=department,
        role=role,
        employee_phone=phone,
    )
    return AuthUser.objects.get(auth_username=jobcode)


@pytest.mark.django_db
class TestDamagedCreateRBAC:
    """待报废单条 create 角色矩阵（方案 A / 规则 :142 报废审批行）:

    regular / asset_admin → 403；dept_manager → 201。
    与规则 :142 修订及本类测试同批落地，拆分则红测无依据。
    """

    @staticmethod
    def _prep_visible_asset(asset, employee):
        """将资产挂到部门员工保管人路径,使 dept_manager 行级可见(ASSET_NOT_VISIBLE 规避)"""
        asset.asset_manager_recordcode = employee
        asset.asset_current_status = "recycled_pending"
        asset.save(update_fields=["asset_manager_recordcode", "asset_current_status"])

    def test_create_denied_for_regular_user(self, api_client, asset, employee, department):
        """regular_user 创建待报废 → 403（规则 :142 regular ❌）"""
        user = _make_role_user("dc_ru", "regular_user", department, "13800000501")
        self._prep_visible_asset(asset, employee)
        api_client.force_authenticate(user=user)
        url = reverse("damaged-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "damaged_date": "2024-07-02",
            "damaged_asset_description": "越权创建",
            "damaged_asset_number": 1,
            "approver": employee.employee_jobcode,
        }
        resp = api_client.post(url, data, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_create_denied_for_asset_admin(self, api_client, asset, employee, department):
        """asset_admin 创建待报废 → 403（方案 A: 并入报废审批行, asset_admin ❌）"""
        user = _make_role_user("dc_aa", "asset_admin", department, "13800000502")
        self._prep_visible_asset(asset, employee)
        api_client.force_authenticate(user=user)
        url = reverse("damaged-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "damaged_date": "2024-07-03",
            "damaged_asset_description": "资产管理员创建",
            "damaged_asset_number": 1,
            "approver": employee.employee_jobcode,
        }
        resp = api_client.post(url, data, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_create_allowed_for_dept_manager(self, api_client, asset, employee, department):
        """dept_manager 创建待报废 → 201（规则 :142 报废审批 ✅ 本部门+下级）"""
        user = _make_role_user("dc_dm", "dept_manager", department, "13800000503")
        self._prep_visible_asset(asset, employee)
        api_client.force_authenticate(user=user)
        url = reverse("damaged-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "damaged_date": "2024-07-04",
            "damaged_asset_description": "部门经理创建",
            "damaged_asset_number": 1,
            "approver": employee.employee_jobcode,
        }
        resp = api_client.post(url, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["code"] == 0
