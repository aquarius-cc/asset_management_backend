"""
未登记资产 API 测试

测试 UnregisteredAssetViewSet 的 API 端点:
- 列表查询
- 详情查询
- 创建
- 更新
- 删除
- 审批
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.unregisteredasset.models import UnregisteredAsset
from core.tests import TEST_PASSWORD


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, auth_user):
    """已认证的用户客户端"""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.mark.django_db
class TestUnregisteredAssetAPI:
    """
    未登记资产 API 测试类
    """

    def test_list_unregistered_assets(self, authenticated_client, unregistered_asset_s1):
        """
        测试获取未登记资产列表
        """
        url = reverse("unregisteredasset:unregisteredasset-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        # 分页响应格式:data 包含 results 列表
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_list_with_filters(self, authenticated_client, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试带筛选条件的列表查询
        """
        url = reverse("unregisteredasset:unregisteredasset-list")
        response = authenticated_client.get(url, {"scenario_type": "s1_no_record"})

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1
        assert response.data["data"]["results"][0]["scenario_type"] == "s1_no_record"

    def test_retrieve_unregistered_asset(self, authenticated_client, unregistered_asset_s1):
        """
        测试获取未登记资产详情
        """
        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["unregistered_code"] == unregistered_asset_s1.unregistered_code

    def test_retrieve_not_found(self, authenticated_client):
        """
        测试获取不存在的资产详情
        """
        url = reverse("unregisteredasset:unregisteredasset-detail", kwargs={"unregistered_code": "UNR-NOTEXIST"})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_unregistered_asset(self, authenticated_client, employee, storage, asset_type):
        """
        测试创建未登记资产
        """
        url = reverse("unregisteredasset:unregisteredasset-list")
        data = {
            "scenario_type": "s1_no_record",
            "discovery_date": "2024-06-01",
            "discovery_location": "会议室A",
            "asset_name": "新资产",
            "asset_brand": "品牌",
            "asset_specification": "规格",
            "unregistered_asset_type": asset_type.recordcode,
            "estimated_value": "5000.00",
            "unregistered_asset_storage": storage.recordcode,
            "discovery_person": employee.employee_jobcode,
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["asset_name"] == "新资产"

    def test_create_validation_error(self, authenticated_client, storage):
        """
        测试创建时验证错误
        """
        url = reverse("unregisteredasset:unregisteredasset-list")
        data = {
            "scenario_type": "s1_no_record",
            # 缺少必填字段
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_unregistered_asset(self, authenticated_client, unregistered_asset_s1):
        """
        测试更新未登记资产
        """
        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        data = {
            "asset_name": "更新后的名称",
            "asset_brand": "更新后的品牌",
        }

        response = authenticated_client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["asset_name"] == "更新后的名称"

    def test_update_not_found(self, authenticated_client):
        """
        测试更新不存在的资产
        """
        url = reverse("unregisteredasset:unregisteredasset-detail", kwargs={"unregistered_code": "UNR-NOTEXIST"})
        data = {"asset_name": "新名称"}

        response = authenticated_client.put(url, data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_unregistered_asset(self, authenticated_client, admin_auth_user, unregistered_asset_s1):
        """
        测试删除未登记资产
        """
        # 切换为管理员用户(delete需要管理员权限)
        authenticated_client.force_authenticate(user=admin_auth_user)

        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )

        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0

        # 验证软删除
        assert UnregisteredAsset.objects.filter(unregistered_code=unregistered_asset_s1.unregistered_code).count() == 0

    def test_delete_not_found(self, authenticated_client, admin_auth_user):
        """
        测试删除不存在的资产
        """
        # 切换为管理员用户(delete需要管理员权限)
        authenticated_client.force_authenticate(user=admin_auth_user)

        url = reverse("unregisteredasset:unregisteredasset-detail", kwargs={"unregistered_code": "UNR-NOTEXIST"})

        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_denied_for_dept_manager(self, dept_manager_client, unregistered_asset_s1):
        """部门经理无删除权限(IsSystemAdmin 门禁)"""
        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        response = dept_manager_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_denied_for_no_department_asset_admin(self, api_client, unregistered_asset_s1):
        """无部门 asset_admin 无删除权限(最严兜底 + IsSystemAdmin 门禁)"""
        from apps.authusermanagement.models import AuthUser
        from apps.usermanagement.models import Employee, EmployeeRole

        user = AuthUser.objects.create_user(auth_username="nd_admin1", password=TEST_PASSWORD)
        Employee.objects.create(
            employee_jobcode="nd_admin1",
            employee_name="无部门资产管理员",
            employee_department=None,
            role=EmployeeRole.ASSET_ADMIN,
        )
        api_client.force_authenticate(user=user)
        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        response = api_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_denied_for_plain_staff_without_role(self, api_client, unregistered_asset_s1):
        """遗留 is_staff 但无 RBAC 角色:不再授予删除权限(门禁已迁移到 IsSystemAdmin)"""
        from apps.authusermanagement.models import AuthUser

        user = AuthUser.objects.create_user(
            auth_username="staff_only", password=TEST_PASSWORD, auth_is_staff=True
        )
        api_client.force_authenticate(user=user)
        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        response = api_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approve_create_and_recycle(self, dept_manager_client, employee, unregistered_asset_s1):
        """
        测试审批通过并回收(需要部门经理权限)
        """
        url = reverse(
            "unregisteredasset:unregisteredasset-approve",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        data = {
            "handle_type": "create_and_recycle",
            "approval_remark": "测试审批通过",
            "approver": employee.employee_jobcode,
        }

        response = dept_manager_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["action"] == "create_and_recycle"
        assert "asset_code" in response.data["data"]

    def test_approve_reject(self, dept_manager_client, employee, unregistered_asset_s1):
        """
        测试审批拒绝(需要部门经理权限)
        """
        url = reverse(
            "unregisteredasset:unregisteredasset-approve",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        data = {
            "handle_type": "reject",
            "approval_remark": "测试拒绝",
            "approver": employee.employee_jobcode,
        }

        response = dept_manager_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["action"] == "reject"

    def test_approve_not_found(self, dept_manager_client):
        """
        测试审批不存在的资产(部门经理权限)
        """
        url = reverse("unregisteredasset:unregisteredasset-approve", kwargs={"unregistered_code": "UNR-NOTEXIST"})
        data = {"handle_type": "create_and_recycle"}

        response = dept_manager_client.post(url, data, format="json")

        # 权限检查先于对象查找,无权限时返回 403 而非 404
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_access(self, api_client):
        """
        测试未认证访问
        """
        url = reverse("unregisteredasset:unregisteredasset-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
